from typing import Optional, cast
from aio_pika import exchange
from aio_pika.exchange import ExchangeType
from app.auth.auth_handler import decodeJWT
import json
import asyncio
from fastapi import WebSocket, HTTPException, status
import sys
import aio_pika
from asyncio.exceptions import CancelledError
from aio_pika.message import DeliveryMode
from sqlalchemy.ext.asyncio import AsyncSession

from app.helpers.settings import load_settings_async, settings
from app.helpers.logger import get_log
from app.db import schema
from app.db import crud
from app.helpers.rabbit_helper import get_connection, MessageState
from app.routers.repository import get_notebook
from app.helpers.boto_helper import write_string_to_s3

import logging

logging.getLogger("aio_pika").setLevel(logging.ERROR)


async def cancel_build(build_id: str):
    connection = await get_connection(
        host=settings.RABBIT_HOST_BUILDER, loop=asyncio.get_event_loop()
    )
    build_id = build_id.lower()

    async with connection:
        routing_key = settings.RABBIT_CANCEL_QUEUE_API
        channel = await connection.channel()
        cancel_queue = await channel.declare_queue(routing_key, durable=True)

        cancel_exchange = await channel.declare_exchange("cancel", ExchangeType.FANOUT)
        await cancel_queue.bind(cancel_exchange)
        body = json.dumps(
            {
                "build_id": build_id,
                "command": "cancel",
            }
        )
        message = aio_pika.Message(
            body=body.encode(), delivery_mode=DeliveryMode.NOT_PERSISTENT
        )

        await channel.default_exchange.publish(
            message=message,
            routing_key=routing_key,
        )


async def start_build(build_id: str, command: str = "start"):
    connection = None
    try:
        await load_settings_async()
        from app.helpers.settings import settings

        connection = await get_connection(
            host=settings.RABBIT_HOST_API, loop=asyncio.get_event_loop()
        )
        build_id = build_id.lower()
        routing_key = settings.RABBIT_START_QUEUE_API
        channel = await connection.channel()
        await channel.declare_queue(settings.RABBIT_START_QUEUE_API, durable=True)

        consumer_queue = await channel.declare_queue(build_id, auto_delete=True)

        body = json.dumps(
            {
                "consumer_queue": consumer_queue.name,
                "build_id": build_id,
                "command": command,
            }
        )
        message = aio_pika.Message(
            body=body.encode(), delivery_mode=DeliveryMode.NOT_PERSISTENT
        )

        await channel.default_exchange.publish(
            message=message,
            routing_key=routing_key,
        )

        async with consumer_queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():  # type: ignore
                    parsed_message = json.loads(message.body.decode())
                    if parsed_message["state"] == MessageState.Started:
                        yield json.dumps(parsed_message)
                    if parsed_message["state"] == MessageState.Running:
                        yield json.dumps(parsed_message)
                    elif parsed_message["state"] == MessageState.Cancelled:
                        yield json.dumps(parsed_message)
                        return
                    elif parsed_message["state"] == MessageState.Error:
                        yield json.dumps(parsed_message)
                        return
                    elif parsed_message["state"] == MessageState.Finished:
                        yield json.dumps(parsed_message)
                        return

    except CancelledError:
        pass
    except Exception:
        get_log(name=__name__).error(str(sys.exc_info()[1]), exc_info=True)
    finally:
        if connection != None:
            try:
                await connection.close()  # type: ignore
            except:
                pass


async def start(websocket: WebSocket, session: AsyncSession):
    try:
        await websocket.accept()
        jwt = None
        build_id: Optional[str] = None
        while True:
            text = await websocket.receive_text()

            input_data = json.loads(text)
            if "command" in input_data:
                command = input_data["command"]
            if "jwt" in input_data:
                jwt = input_data["jwt"]
            if "build_id" in input_data:
                build_id = input_data["build_id"]

            if jwt == None or build_id == None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid GitHub permissions",
                )

            token: schema.Token = decodeJWT(jwt)
            build: schema.Build = await crud.get_build_by_id(
                session=session, build_id=build_id
            )
            if str(build.user_id) != str(token.user_id):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid GitHub permissions",
                )

            if command == "cancel":
                get_log(name=__name__).info(f"Cancelling build for ${build_id}")
                await cancel_build(build_id=cast(str, build_id))
                return

            get_log(name=__name__).info(f"Queuing build for ${build_id}")

            if build.status == schema.BuildStatus.Started:
                async for item in start_build(build_id=cast(str, build_id)):
                    await websocket.send_text(item)
                return

            success = await crud.update_build(
                session=session,
                build_id=build_id,
                update_values={"status": schema.BuildStatus.Queued},
            )

            if success == False:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Build not found"
                )

            build = await crud.get_build_by_id(session=session, build_id=build_id)
            notebook: schema.Notebook = await get_notebook(
                github_username=build.github_username,
                repo_name=build.repository,
                branch_name=build.branch,
                notebook_path=build.notebook,
                token=token,
                session=session,
            )

            s3_uri = f"s3://{settings.AWS_BUILD_LOG_BUCKET}/{build_id}/notebook.ipynb"
            await write_string_to_s3(notebook.contents, s3_uri)

            commit: str = (
                f"\r\nCommit: {build.commit}\r\n" if build.commit != None else ""
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "message": f"ADDING BUILD TO QUEUE\r\n\r\n",
                        "state": MessageState.Started,
                    }
                )
            )

            async for item in start_build(build_id=cast(str, build_id)):
                await websocket.send_text(item)

    except Exception as e:
        if str(type(e)) == "<class 'starlette.websockets.WebSocketDisconnect'>":
            return

        message = str(sys.exc_info()[1])
        get_log(name=__name__).error(message, exc_info=True)
    finally:
        if websocket != None:
            await websocket.close()
