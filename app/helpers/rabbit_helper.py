from enum import Enum
from typing import List, cast
import aio_pika
from aio_pika.exchange import Exchange
from aio_pika.robust_channel import RobustChannel
from dotenv.main import resolve_variables
from app.helpers.logger import get_log
import asyncio
import json
from aio_pika.channel import Channel
from app.helpers.settings import settings


class MessageState(str, Enum):
    Started = "Started"
    Running = "Running"
    Error = "Error"
    Cancelled = "Cancelled"
    Finished = "Finished"


async def get_connection(loop):
    return await aio_pika.connect_robust(
        f"{settings.RABBIT_HOST}",
        loop=loop,
    )


async def empty_queue(queue_name: str):
    connection = None
    try:
        connection = await get_connection(loop=asyncio.get_event_loop())
        channel = await connection.channel()
        queue = await channel.get_queue(settings.RABBIT_START_QUEUE)
        await queue.delete(if_empty=False, if_unused=False)
    except Exception as e:
        if str(type(e)) == "<class 'aiormq.exceptions.ChannelNotFoundEntity'>":
            pass
    finally:
        if connection:
            await connection.close()


async def send_to_queue(
    channel: RobustChannel,
    queue_name: str,
    state: MessageState,
    message=None,
):
    body = json.dumps({"state": state, "message": message})
    try:
        message = aio_pika.Message(body=body.encode())
        exchange = cast(Exchange, channel.default_exchange)
        await asyncio.sleep(0.01)
        await exchange.publish(message=message, routing_key=queue_name)
    except Exception as e:
        get_log(name=__name__).error(f"error with builder", exc_info=True)
