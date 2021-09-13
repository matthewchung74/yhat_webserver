# import databases
# import sqlalchemy
# from fastapi import FastAPI
# from pydantic import BaseModel


from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
import sqlalchemy as sa

from app.helpers.settings import settings


engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI, echo=False, poolclass=NullPool
)
Base = declarative_base()
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_models():
    async with engine.begin() as conn:
        result = await conn.execute(
            sa.text(f"CREATE EXTENSION IF NOT EXISTS pgcrypto;"),
        )

        await conn.run_sync(Base.metadata.create_all)


async def dispose():
    await engine.dispose()


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
