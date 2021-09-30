from async_asgi_testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio
import sqlalchemy as sa
from app.api import app
from app.auth import auth_bearer
from app.helpers.settings import settings
import pytest
import sys
from app.helpers.rabbit_helper import MessageState, empty_queue
from app.helpers.boto_helper import get_s3_client

from app.routers import user


@pytest.fixture
async def client():
    async with TestClient(app) as client:
        yield client


async def delete_table(conn, table_name: str):
    try:
        result = await conn.execute(
            sa.text(f"TRUNCATE TABLE {table_name}"),
        )
        result = await conn.execute(
            sa.text(f"DROP TABLE {table_name}"),
        )
        await conn.commit()
    except:
        # table does not exist
        if sys.exc_info()[0].code == "f405":  # type: ignore
            pass
        else:
            raise


@pytest.mark.asyncio
def test_s3_cleanup():
    async def async_main():
        await empty_queue()
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
def test_table_cleanup():
    async def async_main():
        engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URI,
            echo=False,
        )
        async with engine.connect() as conn:
            try:
                result = await conn.execute(
                    sa.text("TRUNCATE TABLE run"),
                )
                result = await conn.execute(
                    sa.text("DROP TABLE run"),
                )
                result = await conn.execute(
                    sa.text("TRUNCATE TABLE model"),
                )
                result = await conn.execute(
                    sa.text("DROP TABLE model"),
                )
                await conn.commit()
                result = await conn.execute(
                    sa.text("TRUNCATE TABLE build"),
                )
                result = await conn.execute(
                    sa.text("DROP TABLE build"),
                )
                await conn.commit()
                result = await conn.execute(
                    sa.text("TRUNCATE TABLE user_account"),
                )
                result = await conn.execute(
                    sa.text("DROP TABLE user_account"),
                )
                result = await conn.execute(
                    sa.text("DROP TABLE early_access"),
                )
                await conn.commit()
            except:
                # table does not exist
                if sys.exc_info()[0].code == "f405":
                    pass
                else:
                    raise

        await engine.dispose()

    asyncio.run(async_main())


@pytest.mark.asyncio
def test_table_early_access(client):
    async def async_main():
        engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URI,
            echo=False,
        )
        async with engine.connect() as conn:
            try:
                result = await conn.execute(
                    sa.text(
                        "INSERT INTO early_access (email) VALUES ('mclabs74@gmail.com')"
                    ),
                )
                await conn.commit()
            except:
                # table does not exist
                if sys.exc_info()[0].code == "f405":
                    pass
                else:
                    raise

        await engine.dispose()

    asyncio.run(async_main())


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
async def test_fetch_me(client, storage):
    # fetch me
    def mock_func(_):
        return "Bearer", storage["token"]

    auth_bearer.get_cookies = mock_func

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {storage['token']}",
    }

    response = await client.get("/user/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == storage["user_id"]
    assert "github_username" in response.json()
    storage["github_username"] = response.json()["github_username"]
