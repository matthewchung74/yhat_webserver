from typing import List
from async_asgi_testclient import TestClient
from sqlalchemy.sql.expression import update
from app.api import app
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from app.routers import user

from app.helpers.logger import get_log
from app.helpers.settings import settings

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
async def test_fetch_runs(client, storage):

    headers = {"Accept": "application/json"}

    response = await client.get(f"/model/", headers=headers)
    assert response.status_code == 200
    models: List[schema.Model] = [schema.Model(**m) for m in response.json()]

    model_id: str = models[0].id
    build_id: str = models[0].active_build_id
    user_id: str = models[0].user_id

    response = await client.get(f"/run/?model_id={model_id}", headers=headers)
    assert response.status_code == 200
    runs: List[schema.Run] = [schema.Run(**m) for m in response.json()]
    assert len(runs) > 0
    for run in runs:
        assert run.model_id == model_id

    response = await client.get(
        f"/run/?model_id={model_id}&build_id={build_id}", headers=headers
    )
    assert response.status_code == 200
    runs: List[schema.Run] = [schema.Run(**m) for m in response.json()]
    assert len(runs) > 0
    for run in runs:
        assert run.model_id == model_id
        assert run.build_id == build_id

    response = await client.get(
        f"/run/?model_id={model_id}&build_id={build_id}&user_id={user_id}",
        headers=headers,
    )
    assert response.status_code == 200
    runs: List[schema.Run] = [schema.Run(**m) for m in response.json()]
    assert len(runs) > 0
    for run in runs:
        assert run.model_id == model_id
        assert run.build_id == build_id
