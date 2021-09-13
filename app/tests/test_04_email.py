import pathlib
from app.db.schema import BuildStatus, ModelStatus
from async_asgi_testclient import TestClient
from sqlalchemy.sql.expression import update
from app.api import app
import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from yhat_params.yhat_tools import FieldType
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from pathlib import Path

from app.helpers.logger import get_log
from app.helpers.settings import settings
from app.routers import user
from app.db import crud
from app.db import schema
from app.helpers.rabbit_helper import MessageState
from app.helpers.email_helper import send_build_email


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
def test_fetch_a_model(client, storage):
    async def async_main():
        engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URI,
            echo=False,
        )

        async_session = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as session:
            builds: schema.Build = await crud.get_build(
                session=session, status=MessageState.Finished
            )
            build = builds[0]
            build = await crud.get_build_by_id(session=session, build_id=build.id)
            user = await crud.get_user(session=session, user_id=build.user_id)
            await send_build_email(
                user=user,
                build=build,
                build_status=BuildStatus.Finished,
            )

    asyncio.run(async_main())
