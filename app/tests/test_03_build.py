from pathlib import Path
import shutil
from app.db.schema import BuildStatus, ModelStatus
from async_asgi_testclient import TestClient
from sqlalchemy import exc
from app.api import app
import json
from app.auth import auth_bearer
import pytest
import asyncio
import boto3
import os
from app.helpers.logger import get_log

from app.helpers.settings import settings
from app.helpers.rabbit_helper import MessageState, empty_queue
from app.helpers.boto_helper import get_s3_client

import nest_asyncio

nest_asyncio.apply()

from app.helpers.file_helper import (
    STARTING_BUILD_FOR,
    STARTING_DOCKER_BUILD,
    STARTING_FUNCTION_TESTING,
    PUSHING_DOCKER_TO_AWS,
    FINISHED_BUILD,
    CANCELLED_BUILD,
)


@pytest.fixture
async def client():
    async with TestClient(app, use_cookies=True, timeout=1200) as client:
        yield client


@pytest.mark.asyncio
def test_s3_cleanup():
    async def async_main():
        await empty_queue(settings.RABBIT_START_QUEUE_API)
        try:
            bucket_key = settings.AWS_BUILD_LOG_BUCKET
            bucket = get_s3_client().Bucket(bucket_key)
            bucket.objects.all().delete()
        except Exception as e:
            if str(type(e)) == "<class 'botocore.errorfactory.NoSuchBucket'>":
                pass
            else:
                raise

        try:
            bucket_key = settings.AWS_REQUESTS_LOG_BUCKET
            bucket = get_s3_client().Bucket(bucket_key)
            bucket.objects.all().delete()
        except Exception as e:
            if str(type(e)) == "<class 'botocore.errorfactory.NoSuchBucket'>":
                pass
            else:
                raise

    asyncio.run(async_main())


@pytest.mark.asyncio
async def test_create_builds(client, storage, builder_job):

    # fetch me
    def mock_func(_):
        return "Bearer", storage["token"]

    auth_bearer.get_cookies = mock_func

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {storage['token']}",
    }

    if bool(os.getenv("TEST_ALL_MODELS")) == True:
        notenooks = [
            "yolov5/pretrained_pil_inference.ipynb",
            # "yolov5/pretrained_cv2_inference.ipynb",
            # "huggingface/imdb_classification_inference.ipynb",
            # "huggingface/question_answering_inference.ipynb",
        ]
    else:
        notenooks = ["yolov5/unit_test_inference.ipynb"]

    github_username = "mclabs74"
    repository = "inference_nbs"
    branch = "dev"
    storage["builds"] = []
    storage["models"] = []

    for notebook in notenooks:
        data = {
            "github_username": github_username,
            "repository": repository,
            "branch": branch,
            "commit": "046b52ae9cd40e337bee115bba1460f7cc9469ad",
            "notebook": notebook.replace("/", "|"),
            "user_id": storage["user_id"],
            "input_json": {"a": "b"},
        }

        response = await client.post("/build/", json=data, headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] != None
        assert response.json()["model_id"] != None
        build_id = response.json()["id"]
        model_id = response.json()["model_id"]
        storage["builds"].append(build_id)
        storage["models"].append(model_id)


@pytest.mark.asyncio
async def test_fetch_build(client, storage):

    headers = {"Accept": "application/json"}

    response = await client.get(f"/build/{storage['builds'][0]}", headers=headers)
    assert response.status_code == 200
    assert str(response.json()["id"]) == str(storage["builds"][0])
    assert str(response.json()["status"]) == BuildStatus.NotStarted


async def cancel_build(client, build_id: str, jwt: str):
    try:
        async with client.websocket_connect("/ws") as ws:
            await ws.send_str(
                json.dumps({"build_id": build_id, "jwt": jwt, "command": "cancel"})
            )

            await ws.receive_text()
    except:
        pass


@pytest.mark.asyncio
async def test_ws_cancel_endpoint(client, storage):
    try:
        build_id = storage["builds"][0]
        jwt = storage["token"]

        await cancel_build(client=client, build_id=build_id, jwt=jwt)

        async with client.websocket_connect("/ws") as ws:
            await ws.send_str(
                json.dumps({"build_id": build_id, "jwt": jwt, "command": "start"})
            )

            result = []
            msg = await ws.receive_text()
            result.append(json.loads(msg))
            while msg != None:
                msg = await ws.receive_text()
                data = json.loads(msg)
                result.append(data)
                get_log(name=__name__).debug(f"{data['state']} {data['message']}")
                if data["state"] == MessageState.Finished:
                    break
                elif data["state"] == MessageState.Error:
                    break
                elif data["state"] == MessageState.Cancelled:
                    break

        messages = [r["message"] for r in result]
        assert CANCELLED_BUILD in " ".join(messages)
        await asyncio.sleep(0.2)
    except Exception as e:
        get_log(name=__name__).error("", exc_info=True)
        raise e


@pytest.mark.asyncio
async def test_fetch_model_no_build(client, storage):

    headers = {"Accept": "application/json"}

    response = await client.get(f"/model/{storage['models'][0]}", headers=headers)
    assert response.status_code == 200
    assert str(response.json()["id"]) == str(storage["models"][0])
    assert str(response.json()["status"]) == ModelStatus.Draft


async def run_ws_endpoint(client, build_id, jwt):

    tmp_dir = Path(f"/tmp/{build_id}")
    app_dir = tmp_dir / "app"
    shutil.rmtree(tmp_dir, ignore_errors=True)

    try:
        async with client.websocket_connect("/ws") as ws:
            await ws.send_str(
                json.dumps({"build_id": build_id, "jwt": jwt, "command": "start"})
            )
            result = []
            msg = await ws.receive_text()
            result.append(json.loads(msg))
            while msg != None:
                msg = await ws.receive_text()
                data = json.loads(msg)
                result.append(data)
                get_log(name=__name__).debug(f"{data['state']} {data['message']}")
                if data["state"] == MessageState.Finished:
                    break
                elif data["state"] == MessageState.Error:
                    break
                elif data["state"] == MessageState.Cancelled:
                    break

            messages = [r["message"] for r in result]
            assert STARTING_BUILD_FOR in " ".join(messages)
            assert STARTING_DOCKER_BUILD in " ".join(messages)
            assert STARTING_FUNCTION_TESTING in " ".join(messages)
            assert PUSHING_DOCKER_TO_AWS in " ".join(messages)
            assert FINISHED_BUILD in " ".join(messages)
    except Exception as e:
        get_log(name=__name__).error("", exc_info=True)
        raise e


@pytest.mark.asyncio
async def test_ws_endpoint(client, storage):
    build_id = storage["builds"][0]
    jwt = storage["token"]
    loop = asyncio.get_event_loop()

    coroutines = []
    for build in storage["builds"]:
        coroutines.append(run_ws_endpoint(client=client, jwt=jwt, build_id=build))

    try:
        group = asyncio.gather(*coroutines)

        loop.run_until_complete(group)
        assert True
    except Exception as e:
        get_log(name=__name__).error("", exc_info=True)
        if group != None:
            group.cancel()

        raise e


@pytest.mark.asyncio
async def test_fetch_model_with_build(client, storage):
    headers = {"Accept": "application/json"}

    response = await client.get(f"/model/{storage['models'][0]}", headers=headers)
    assert response.status_code == 200
    assert str(response.json()["id"]) == str(storage["models"][0])
    assert "active_build_id" in response.json()
