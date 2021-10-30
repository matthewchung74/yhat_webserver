from dotenv import load_dotenv

load_dotenv()

from multiprocessing import Process
from typing import Awaitable, Callable, Dict, List
from aio_pika import exchange
from aio_pika.exchange import ExchangeType
from app.helpers.file_helper import (
    BuilderException,
    CANCELLED_BUILD,
    CancelledException,
    cancel_if_needed,
    delete_cancel_if_needed,
)

from app.helpers.rabbit_helper import (
    get_connection,
    send_to_queue,
)
import functools
from threading import Thread
from aio_pika.message import IncomingMessage

import asyncio
from aio_pika.connection import ConnectionType
import json

from sqlalchemy.pool import NullPool
from app.helpers.logger import get_log
from pathlib import Path
import os
import docker
import socket
from app.db import schema
from app.db import crud
from app.helpers.settings import settings
from app.service.builder_server import docker_builder, lambda_builder
import shutil
import boto3

import sys
from app.helpers.asyncwrapper import async_wrap
import time
import aiofiles

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from app.helpers.file_helper import sample_params_from_input_json

from app.helpers.boto_helper import (
    invoke_lambda_function,
    read_string_from_s3,
    get_ecr_public_client,
    write_file_to_s3,
    get_ecr_private_client,
)
from app.helpers.rabbit_helper import MessageState, get_connection
from app.helpers.file_helper import (
    STARTING_BUILD_FOR,
    STARTING_DOCKER_BUILD,
    STARTING_FUNCTION_TESTING,
    PUSHING_DOCKER_TO_AWS,
    TESTING_IN_CLOUD,
    FINISHED_BUILD,
)

from app.helpers.email_helper import send_build_email
from ec2_metadata import ec2_metadata

cancel_list: List = []
prefetch_count = 4
build_count = 0

ecr_repository_name = settings.ECR_REPOSITORY_NAME
aws_account_id = settings.AWS_ACCOUNT_ID

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI, echo=False, poolclass=NullPool
)
Base = declarative_base()
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def download_notebook_from_s3(s3_uri: str, tmp_dir):
    notebook_contents = await read_string_from_s3(s3_uri=s3_uri)

    script_out = f"{tmp_dir}/notebook.ipynb"
    if os.path.exists(script_out):
        os.remove(script_out)

    with open(script_out, "w") as file_out:
        file_out.write(notebook_contents)

    return script_out


def create_work_directories(build_id: str):
    tmp_dir = Path(f"/tmp/{build_id}")
    app_dir = tmp_dir / "app"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir)
    os.makedirs(app_dir)


async def push_to_aws(
    username: str,
    password: str,
    docker_client: docker.APIClient,
    image_uri: str,
    cancel_if_needed_partial: Callable,
    log_output,
    triedCount=0,
):
    try:
        auth_config_payload = {"username": username, "password": password}
        gen = docker_builder.push_to_aws(
            docker_client=docker_client,
            image_uri=image_uri,
            auth_config_payload=auth_config_payload,
            cancel_if_needed=cancel_if_needed_partial,
        )

        for message in gen:
            await log_output(
                message=message, state=MessageState.Running, include_newline=False
            )

    except CancelledException:
        raise
    except Exception as e:
        if triedCount < 20:
            await log_output(
                message="\r\nPush to aws timed out, waiting 1 min and retrying...\r\n",
                state=MessageState.Running,
            )
            await asyncio.sleep(60)

            await push_to_aws(
                username=username,
                password=password,
                docker_client=docker_client,
                image_uri=image_uri,
                cancel_if_needed_partial=cancel_if_needed_partial,
                log_output=log_output,
                triedCount=1 + triedCount,
            )
        else:
            raise


def start_build_thread(body: Dict, build_index: int):
    proc = Process(
        name=str(build_index),
        target=start_build_sync,
        args=(
            body["consumer_queue"],
            body["build_id"],
            build_index,
        ),
        daemon=True,
    )

    proc.start()
    # uncomment for rabbit acks
    # proc.join()


def start_build_sync(queue_name, build_id, build_index):

    try:
        asyncio.run(
            start_build(
                queue_name=queue_name,
                build_id=build_id,
                build_index=build_index,
            )
        )
    except RuntimeError as re:
        if "There is no current event loop in thread" in str(re):
            loop = asyncio.new_event_loop()
            task = loop.create_task(
                start_build(
                    queue_name=queue_name, build_id=build_id, build_index=build_index
                )
            )
            loop.run_until_complete(asyncio.wait([task]))


async def start_build(queue_name: str, build_id: str, build_index: int):
    async with async_session() as session:
        await start_build_with_session(
            queue_name=queue_name,
            build_id=build_id,
            session=session,
            build_index=build_index,
        )


class LBTimer:
    def __init__(self, start_channel):
        Thread.__init__(self)
        self.start_channel = start_channel
        self._task = asyncio.ensure_future(self._job())

    async def _job(self):
        try:
            if settings.LOAD_BALANCE_ARN == None:
                get_log(name=__name__).info("LBTimer not running on AWS")
                return

            while settings.LOAD_BALANCE_ARN != None:
                await asyncio.sleep(5)

                from ec2_metadata import ec2_metadata

                instance_id: str = ec2_metadata.instance_id
                import boto3

                client = boto3.client("elbv2", region_name=settings.AWS_REGION_NAME)

                response = client.describe_target_groups(
                    LoadBalancerArn=settings.LOAD_BALANCE_ARN
                )
                target_group_arn = response["TargetGroups"][0]["TargetGroupArn"]

                response = client.describe_target_health(
                    TargetGroupArn=target_group_arn
                )

                instances = list(
                    map(
                        lambda x: (x["Target"]["Id"], x["TargetHealth"]["State"]),
                        response["TargetHealthDescriptions"],
                    )
                )

                for instance in instances:
                    if instance_id == instance[0] and instance[1] == "draining":
                        await self.start_channel.close()
                        get_log(name=__name__).info(
                            f"builder instance {instance_id} not found in target group {instances}, closing channel"
                        )
                        return

                get_log(name=__name__).info(
                    f"builder instance {instance_id} in target group {instances}"
                )
        except:
            get_log(name=__name__).error(f"Error in LBTimer", exc_info=True)
            pass


async def start_build_with_session(
    queue_name: str,
    build_id: str,
    session: AsyncSession,
    build_index: int,
):

    docker_client = None
    rabbit_connection = None
    script_py = None
    docker_image_id = None

    try:
        build_time_start = time.time()

        loop = asyncio.get_event_loop()
        ecr_private_client = get_ecr_private_client()
        ecr_public_client = get_ecr_public_client()

        rabbit_connection = await get_connection(
            host=settings.RABBIT_HOST_BUILDER, loop=asyncio.get_event_loop()
        )
        channel = await rabbit_connection.channel()

        tmp_dir = Path(f"/tmp/{build_id}")
        app_dir = tmp_dir / "app"
        log_file = tmp_dir / "log.txt"

        async def log_output(message: str, state: MessageState, include_newline=True):

            if "\r\n" in message:
                pass
            elif "\n" in message:
                message = message.replace("\n", "\r\n")

            get_log(name=__name__).info(message)

            await send_to_queue(
                channel=channel,
                queue_name=queue_name,
                state=state,
                message=message,
            )

            async with aiofiles.open(log_file, "a") as my_log:
                if include_newline:
                    await my_log.write(f"{message}\r\n")
                else:
                    await my_log.write(message)

        cancel_if_needed_partial = functools.partial(
            cancel_if_needed, build_id=build_id
        )

        build: schema.Build = await crud.get_build_by_id(
            session=session, build_id=build_id
        )
        if build == None:
            raise BuilderException(message="Build not found", build_id=build_id)

        if build.status == schema.BuildStatus.Error:
            raise BuilderException(message="Build already errored", build_id=build_id)

        user: schema.User = await crud.get_user(session=session, user_id=build.user_id)
        if user == None:
            raise BuilderException(
                message="User owner of build not found", build_id=build_id
            )

        cancel_if_needed_partial()

        create_work_directories(build_id=build_id)

        await crud.update_build(
            session=session,
            build_id=build.id,
            update_values={
                "worker_server": socket.gethostname(),
                "status": schema.BuildStatus.Started,
            },
        )

        s3_base_url = f"s3://{settings.AWS_BUILD_LOG_BUCKET}/{build.id}"

        await log_output(
            message=f"\r\n{STARTING_BUILD_FOR} {build.notebook}\r\nCOMMIT {build.commit}\r\nBUILD_ID:{build.id}\r\n\r\n",
            state=MessageState.Running,
        )

        nb_path = await download_notebook_from_s3(
            s3_uri=f"{s3_base_url}/notebook.ipynb", tmp_dir=tmp_dir
        )

        convert_to_py_partial = functools.partial(
            docker_builder.convert_to_py, nb_path=nb_path
        )
        script_nb, script_py = await loop.run_in_executor(None, convert_to_py_partial)

        await log_output(
            message=f"\r\nConverted {build.notebook} to inference.ipynb and inference.py",
            state=MessageState.Running,
        )

        docker_builder.copy_to_app(
            script_nb=script_nb,
            script_py=script_py,
            app_dir=app_dir,
            tmp_dir=tmp_dir,
        )

        trimmed_user_name = user.github_username[:20]
        trimmed_repo_name = build.repository[:20]
        trimmed_script_name = Path(Path(build.notebook).stem.replace("|", "/")).name[
            :20
        ]
        tag = f"{ecr_repository_name}:{trimmed_user_name}_{trimmed_repo_name}_{trimmed_script_name}"

        await log_output(
            message=f"\r\n\r\n{STARTING_DOCKER_BUILD}\r\n", state=MessageState.Running
        )

        try:
            docker_client = docker.APIClient(base_url="unix://var/run/docker.sock")
        except:
            get_log(name=__name__).error(f"builder:{build_id} error", exc_info=True)
            raise BuilderException(
                "Docker error, check to make sure daemon is running", build_id=build_id
            )

        username, password, registry = docker_builder.login_aws(
            docker_client=docker_client,
            ecr_private_client=ecr_private_client,
            ecr_public_client=ecr_public_client,
            aws_account_id=aws_account_id,
            build_id=build_id,
        )

        # docker_builder.pull_base(docker_client=docker_client)

        image_uri = f"{registry.replace('https://', '')}/{tag}"

        gen = docker_builder.convert_to_docker(
            docker_client=docker_client,
            tag=tag,
            tmp_dir=str(tmp_dir),
            build_id=build_id,
            cancel_if_needed=cancel_if_needed_partial,
        )

        for line_payload in gen:
            # for line_payload in line_payloads:
            message = line_payload["message"]
            if line_payload["type"] == "error":
                raise BuilderException(message=message, build_id=build_id)
            elif line_payload["type"] == "message":
                if "Successfully built" in message and len(message.split()) == 3:
                    docker_image_id = message.split()[2]

                await log_output(message=message, state=MessageState.Running)

        if docker_image_id == None:
            raise BuilderException(
                message="docker_image_id not found in docker build", build_id=build_id
            )

        docker_image_size = docker_builder.inspect_image(
            docker_client=docker_client, tag=tag, build_id=build_id
        )

        await crud.update_build(
            session=session,
            build_id=build_id,
            update_values={
                "docker_image_size": round(docker_image_size / 1000000),
            },
        )

        await log_output(
            message=f"\r\n{STARTING_FUNCTION_TESTING}\r\n", state=MessageState.Running
        )

        gen = docker_builder.test_build_docker(
            docker_client=docker_client,
            image_uri=image_uri,
            docker_tag=tag,
            build_id=build_id,
            build_index=build_index,
        )

        for line_payload in gen:
            message = line_payload["message"]
            if line_payload["type"] == "error":
                with open(log_file, "a") as my_log:
                    my_log.writelines([message])
                raise BuilderException(message=message, build_id=build_id)
            elif line_payload["type"] == "input_json":
                await crud.update_build(
                    session=session,
                    build_id=build.id,
                    update_values={
                        "input_json": json.loads(message),
                    },
                )
            elif line_payload["type"] == "output_json":
                await crud.update_build(
                    session=session,
                    build_id=build.id,
                    update_values={
                        "output_json": json.loads(message),
                    },
                )
            else:
                await log_output(message=f"\r\n{message}", state=MessageState.Running)

        docker_builder.tag_image(
            docker_client=docker_client,
            tag=tag,
            image_uri=image_uri,
        )

        await log_output(
            message=f"\r\n\r\n{PUSHING_DOCKER_TO_AWS}\r\n", state=MessageState.Running
        )
        await log_output(
            message="\r\nTake a break or get some coffee, we still have 10 or so minutes to go.\r\n",
            state=MessageState.Running,
        )

        await push_to_aws(
            username=username,
            password=password,
            docker_client=docker_client,
            image_uri=image_uri,
            cancel_if_needed_partial=cancel_if_needed_partial,
            log_output=log_output,
        )

        cancel_if_needed_partial()

        lambda_function_name = tag.split(":")[1]

        lambda_exists = lambda_builder.lambda_function_exists(
            function_name=lambda_function_name
        )
        if lambda_exists:
            lambda_builder.delete_lambda(function_name=lambda_function_name)

        gen = lambda_builder.deploy_lambda(
            lambda_function_name,
            image_uri,
            {"user_id": str(user.id), "build_id": build_id},
            cancel_if_needed=cancel_if_needed_partial,
        )

        function_arn = None
        for line_payload in gen:
            message = line_payload["message"]
            if line_payload["type"] == "error":
                with open(log_file, "a") as my_log:
                    my_log.writelines([message])
                raise BuilderException(message=message, build_id=build_id)
            elif line_payload["type"] == "arn":
                function_arn = message
            elif line_payload["type"] == "dot":
                await log_output(
                    message=message, state=MessageState.Running, include_newline=False
                )
            else:
                await log_output(message=message, state=MessageState.Running)

        await crud.update_build(
            session=session,
            build_id=build_id,
            update_values={
                "lambda_function_arn": function_arn,
                "docker_image_uri": image_uri,
            },
        )

        await log_output(
            message=f"\r\n\r\n{TESTING_IN_CLOUD}\r\n", state=MessageState.Running
        )

        build = await crud.get_build_by_id(session=session, build_id=build_id)

        input_json = build.input_json
        myobj = sample_params_from_input_json(params=input_json)
        myobj["request_id"] = build_id
        myobj["output_bucket_name"] = settings.AWS_REQUESTS_LOG_BUCKET
        function_params = {"body": myobj}
        await invoke_lambda_function(
            function_name=lambda_function_name, function_params=function_params
        )

        build_time_duration = round((time.time() - build_time_start), 2)

        await log_output(
            message=f"\r\n\r\n{FINISHED_BUILD} in {build_time_duration}s \r\n",
            state=MessageState.Finished,
        )

        await crud.update_build(
            session=session,
            build_id=build.id,
            update_values={
                "status": schema.BuildStatus.Finished,
                "duration": build_time_duration,
            },
        )

        await crud.update_model(
            session=session,
            model_id=build.model_id,
            update_values={
                "active_build_id": build_id,
                "commit": build.commit if build.commit else None,
                "branch": build.branch,
                "status": schema.ModelStatus.Public,
            },
        )

        build_status: schema.BuildStatus = schema.BuildStatus.Finished

    except CancelledException:
        try:
            await crud.update_build(
                session=session,
                build_id=build_id,
                update_values={
                    "status": schema.BuildStatus.Cancelled,
                },
            )
            await log_output(
                message=f"\r\n{CANCELLED_BUILD}\r\n", state=MessageState.Cancelled
            )

            delete_cancel_if_needed(build_id=build_id)

            build_status = schema.BuildStatus.Cancelled
        except:
            pass
        return
    except Exception:
        try:
            message = f"\r\n{str(sys.exc_info()[1])}"
            await log_output(message=message, state=MessageState.Error)
            get_log(name=__name__).error(f"builder:{build_id} error", exc_info=True)

            await crud.update_build(
                session=session,
                build_id=build.id,
                update_values={
                    "status": schema.BuildStatus.Error,
                },
            )

            build_status = schema.BuildStatus.Error

        except:
            pass
    finally:
        try:
            if docker_image_id != None and docker_client != None:
                docker_builder.prune_images(
                    docker_client=docker_client,
                    docker_image_id=docker_image_id,
                )
        except Exception as e:
            pass

        if docker_client:
            await loop.run_in_executor(None, docker_client.close)

        if rabbit_connection:
            await rabbit_connection.close()

        try:
            if log_file:
                await write_file_to_s3(
                    log_file, f"{build_id}/log.txt", settings.AWS_BUILD_LOG_BUCKET
                )

                build_log = f"s3://{settings.AWS_BUILD_LOG_BUCKET}/{build_id}/log.txt"
                await crud.update_build(
                    session=session,
                    build_id=build.id,
                    update_values={
                        "build_log": build_log,
                    },
                )

                build.build_log = build_log
                await send_build_email(
                    user=user,
                    build=build,
                    build_status=build_status,
                )

        except:
            pass

        try:
            if script_py:
                await write_file_to_s3(
                    script_py, f"{build_id}/inference.py", settings.AWS_BUILD_LOG_BUCKET
                )
        except:
            pass


async def on_message(message: IncomingMessage):
    async with message.process():
        get_log(name=__name__).info(f"received message {str(message.body)}")

        global build_count
        build_count += 1
        build_index = build_count % prefetch_count

        body = json.loads(message.body)
        if "command" in body and body["command"] == "cancel":
            Path(f"/tmp/{body['build_id']}").mkdir(parents=True, exist_ok=True)
            cancel_file = Path(f"/tmp/{body['build_id']}/cancel.txt")
            try:
                async with aiofiles.open(cancel_file, "w") as out:
                    await out.write("cancel")
                    await out.flush()
            except:
                pass
        else:
            loop = asyncio.get_event_loop()
            start_build_thread_partial = functools.partial(
                start_build_thread, body=body, build_index=build_index
            )
            await loop.run_in_executor(None, start_build_thread_partial)


async def main(loop):
    try:

        get_log(name=__name__).info(f"Starting API Builder")

        connection = await get_connection(host=settings.RABBIT_HOST_BUILDER, loop=loop)
        start_channel = await connection.channel()
        await start_channel.set_qos(prefetch_count=prefetch_count)

        start_queue = await start_channel.declare_queue(
            settings.RABBIT_START_QUEUE_BUILDER,
            durable=True,
        )

        consumer_tag = await start_queue.consume(
            on_message, no_ack=False, timeout=60 * 30
        )

        cancel_channel = await connection.channel()
        cancel_queue = await cancel_channel.declare_queue(
            settings.RABBIT_CANCEL_QUEUE_BUILDER,
            durable=True,
        )

        cancel_exchange = await cancel_channel.declare_exchange(
            "cancel", ExchangeType.FANOUT
        )
        await cancel_queue.bind(cancel_exchange)
        await cancel_queue.consume(on_message, no_ack=False, timeout=60 * 30)

        thread = LBTimer(start_channel)

        get_log(name=__name__).info(
            f"builder connected to {settings.RABBIT_HOST_BUILDER.split('@')[0]}://{settings.RABBIT_HOST_BUILDER.split('@')[-1]} listening for messages"
        )

        return connection
    except:
        get_log(name=__name__).error(f"error with builder", exc_info=True)
        raise


def start():
    loop = asyncio.get_event_loop()
    connection = loop.run_until_complete(main(loop))

    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(connection.close())


if __name__ == "__main__":
    start()
