from operator import mod
from typing import List
from async_asgi_testclient import TestClient
from sqlalchemy.sql.expression import update
from app.api import app
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
import sqlalchemy as sa
from app.routers import user

from app.helpers.logger import get_log
from app.helpers.settings import settings
from app.auth import auth_bearer

from app.db import schema
from app.db import crud


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
async def test_fetch_models(client, storage):

    headers = {"Accept": "application/json"}

    response = await client.get(f"/model/", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) >= 0
    storage["models"] = [schema.Model(**j) for j in response.json()]


@pytest.mark.asyncio
async def test_fetch_models_by_user(client, storage):

    headers = {"Accept": "application/json"}

    response = await client.get(
        f"/model/?user_id={storage['user_id']}", headers=headers
    )
    assert response.status_code == 200
    assert len(response.json()) > 0


@pytest.mark.asyncio
async def test_fetch_model_by_id(client, storage):

    headers = {"Accept": "application/json"}

    response = await client.get(f"/model/{storage['models'][0].id}", headers=headers)
    assert response.status_code == 200
    assert "active_build" in response.json()
    assert response.json()["active_build"]["id"] != None


@pytest.mark.asyncio
async def test_me_models(client, storage):

    # fetch me
    def mock_func(_):
        return "Bearer", storage["token"]

    auth_bearer.get_cookies = mock_func

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {storage['token']}",
    }

    response = await client.get(f"/model/me?status=Draft", headers=headers)
    assert response.status_code == 200
    models: List[schema.Model] = [schema.Model(**j) for j in response.json()]
    assert len(models) == 0

    response = await client.get(f"/model/me?status=Public", headers=headers)
    assert response.status_code == 200
    models: List[schema.Model] = [schema.Model(**j) for j in response.json()]
    assert len(models) > 0

    my_model: schema.Model = models[0]
    data: dict = {
        "title": "my new title",
        "description": "my new descirption",
        "credits": "my new credits",
        "release_notes": "my new release notes",
    }

    response = await client.put(f"/model/{my_model.id}", json=data, headers=headers)
    assert response.status_code == 200

    response = await client.get(f"/model/{my_model.id}", headers=headers)
    my_model = schema.Model(**response.json())
    assert my_model.title == data["title"]
    assert my_model.description == data["description"]
    assert my_model.credits == data["credits"]
    assert my_model.active_build.release_notes == data["release_notes"]
