from async_asgi_testclient import TestClient
from sqlalchemy.sql.expression import update
from app.api import app
import pytest

from yhat_params.yhat_tools import FieldType
import copy
import requests
from app.auth import auth_bearer
from pathlib import Path

from app.helpers.logger import get_log
from app.helpers.settings import settings
import uuid

from app.db import schema
from app.routers import user


@pytest.fixture
async def client():
    async with TestClient(app, use_cookies=True, timeout=1200) as client:
        yield client


@pytest.mark.asyncio
async def test_create_github_user(client, storage):
    # github login/auth
    async def mock_func(_):
        return settings.GITHUB_TEST_TOKEN

    user._fetch_github_access = mock_func

    data: dict = {"code": "abc"}
    headers = {"Accept": "application/json"}
    response = await client.post("/user/login/github", json=data, headers=headers)
    assert response.status_code == 200
    assert response.json()["token"] != None
    assert response.json()["user_id"] != None
    storage["token"] = response.json()["token"]
    storage["user_id"] = response.json()["user_id"]


@pytest.mark.asyncio
async def test_get_signed_urls(client, storage):
    def mock_func(_):
        return "Bearer", storage["token"]

    auth_bearer.get_cookies = mock_func

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {storage['token']}",
    }

    response = await client.get(f"/model/", headers=headers)
    assert response.status_code == 200
    storage["models"] = [schema.Model(**m) for m in response.json()]
    storage["signed_urls"] = []
    storage["run_ids"] = []
    for model in storage["models"]:
        run_id: str = str(uuid.uuid1())
        storage["run_ids"].append(run_id)
        response = await client.post(
            f"/signed_url/{model.id}?run_id={run_id}", headers=headers
        )
        assert response.status_code == 200
        storage["signed_urls"].append(response.json())

    assert len(storage["models"]) > 0
    assert len(storage["signed_urls"]) > 0


@pytest.mark.asyncio
async def test_predict_models(client, storage):
    def mock_func(_):
        return "Bearer", storage["token"]

    auth_bearer.get_cookies = mock_func

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {storage['token']}",
    }

    for i, model in enumerate(storage["models"]):
        response = await client.get(f"/model/{model.id}", headers=headers)
        full_model = schema.Model(**response.json())
        signed_urls = storage["signed_urls"][i]
        run_id = storage["run_ids"][i]
        input_copy = copy.deepcopy(full_model.active_build.input_json)
        pil_index = 0
        for index, (key, value) in enumerate(
            full_model.active_build.input_json.items()
        ):
            if FieldType.PIL == value in value:
                # if FieldType.PIL == value or FieldType.OpenCV in value:
                signed_url = signed_urls[pil_index]["url"]
                fields = signed_urls[pil_index]["fields"]
                pil_index += 1
                with open("app/tests/red.jpg", "rb") as f:
                    files = {"file": (key, f)}
                    response = requests.post(
                        signed_url,
                        data=fields,
                        headers={"Accept": "application/json"},
                        files=files,
                    )
                    bucket = Path(signed_url).parts[1].split(".")[0]
                    s3_uri = f"s3://{bucket}/{fields['key']}"
                    input_copy[key] = s3_uri

        response = await client.post(
            f"/prediction/{model.id}?run_id={run_id}", json=input_copy, headers=headers
        )
        result: schema.Run = schema.Run(**response.json())
        assert result.id != None
        assert result.input_json != None
        assert result.output_json != None
