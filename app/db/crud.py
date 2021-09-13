from pathlib import Path
from app.helpers.boto_helper import create_presigned_url
from textwrap import shorten
from typing import List, Optional, Dict
from sqlalchemy import schema, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from sqlalchemy.orm import joinedload

from app.db import model
from app.db import schema


async def create_user_from_github(
    session: AsyncSession, github_user: schema.GithubUser
) -> schema.User:
    stmt = select(model.User).where(model.User.github_id == github_user.github_id)

    result = await session.execute(stmt)
    existing_user = result.scalars().first()
    if existing_user:
        if github_user.dict() != schema.GithubUser.from_orm(existing_user).dict():
            session.begin()
            existing_user.update_from_schema(github_user)
            await session.commit()
        return existing_user
    else:
        new_user = model.User(**dict(github_user))
        session.add(new_user)
        await session.commit()
        user_schema = schema.User.from_orm(new_user)
        return user_schema


async def get_user(session: AsyncSession, user_id: UUID) -> Optional[schema.User]:
    stmt = select(model.User).where(model.User.id == str(user_id))

    result = await session.execute(stmt)
    user = result.scalars().first()
    if user == None:
        return None

    return schema.User.from_orm(user)


async def get_has_early_access(session: AsyncSession, email: str) -> bool:
    stmt = select(model.EarlyAccess).where(model.EarlyAccess.email == email)

    result = await session.execute(stmt)
    existing_build = result.scalars().first()
    if existing_build == None:
        return False

    return True


async def get_build_by_id(session: AsyncSession, build_id: UUID) -> schema.Build:
    stmt = select(model.Build).where(model.Build.id == str(build_id))

    result = await session.execute(stmt)
    existing_build = result.scalars().first()
    if existing_build == None:
        return None

    return schema.Build.from_orm(existing_build)


async def get_build(
    session: AsyncSession,
    model_id: Optional[str] = None,
    user_id: Optional[str] = None,
    github_username: Optional[str] = None,
    repository: Optional[str] = None,
    branch: Optional[str] = None,
    notebook: Optional[str] = None,
    commit: Optional[str] = None,
    status: Optional[str] = None,
) -> List[schema.Run]:

    where_list = []
    if model_id != None:
        where_list.append(model.Build.model_id == model_id)

    if user_id != None:
        where_list.append(model.Build.user_id == user_id)

    if github_username != None:
        where_list.append(model.Build.github_username == github_username)

    if repository != None:
        where_list.append(model.Build.repository == repository)

    if branch != None:
        where_list.append(model.Build.branch == branch)

    if notebook != None:
        where_list.append(model.Build.notebook == notebook)

    if commit != None:
        where_list.append(model.Build.commit == commit)

    if status != None:
        where_list.append(model.Build.status == status)

    stmt = select(model.Build).where(*where_list)

    ret: List[schema.Build] = []
    result = await session.execute(stmt)
    for m in result.scalars():
        build: schema.Build = schema.Build(**m.__dict__)
        ret.append(build)

    return ret


async def create_build(session: AsyncSession, build: schema.Build) -> schema.Build:
    new_build = model.Build(**dict(build))
    session.add(new_build)
    await session.commit()
    build_schema = schema.Build.from_orm(new_build)
    return build_schema


async def update_build(
    session: AsyncSession, build_id: str, update_values: Dict
) -> schema.Build:
    stmt = (
        update(model.Build)
        .where(
            model.Build.id == str(build_id),
        )
        .values(update_values)
        .execution_options(synchronize_session="fetch")
    )

    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount == 1

    # stmt = select(model.Build).where(
    #     model.Build.id == build_id,
    #     model.Build.user_id == str(user_id)
    # )

    # result = await session.execute(stmt)
    # existing_build = result.scalars().first()
    # session.begin()
    # for key, value in update_values.items():
    #     setattr(existing_build, key, value)
    # # foo = existing_build.update(update_values)
    # await session.commit()

    # print(existing_build)
    # new_build = model.Build(**dict(build))
    # session.add(new_build)
    # await session.commit()
    # build_schema = schema.Build.from_orm(new_build)
    # return build_schema


async def get_model_from_build(
    session: AsyncSession, build: schema.Build
) -> schema.Model:
    stmt = select(model.Model).where(
        model.Model.github_username == str(build.github_username),
        model.Model.repository == str(build.repository),
        model.Model.notebook == str(build.notebook),
        model.Model.user_id == str(build.user_id),
    )

    result = await session.execute(stmt)
    existing_model = result.scalars().first()
    if existing_model == None:
        return None

    return schema.Model(**existing_model.__dict__)


async def get_model_by_id(session: AsyncSession, model_id: UUID) -> schema.Model:
    stmt = (
        select(model.Model)
        .where(
            model.Model.id == str(model_id),
        )
        .options(joinedload(model.Model.active_build), joinedload(model.Model.user))
    )

    result = await session.execute(stmt)
    existing_model = result.scalars().first()
    if existing_model == None:
        return None

    return schema.Model.from_orm(existing_model)


async def get_models(
    session: AsyncSession,
    status: schema.ModelStatus = schema.ModelStatus.Public,
    offset: int = 0,
    limit: int = 10,
) -> List[schema.Model]:
    if limit > 100:
        limit = 100
    stmt = (
        select(model.Model)
        .where(
            model.Model.status == status,
        )
        .limit(limit=limit)
        .offset(offset=offset)
    )

    ret: List[schema.Model] = []
    result = await session.execute(stmt)
    for m in result.scalars():
        ret.append(schema.Model(**m.__dict__))

    return ret


async def get_models_by_user_id(
    session: AsyncSession,
    user_id: str,
    status: schema.ModelStatus = schema.ModelStatus.Public,
    offset: int = 0,
    limit: int = 10,
) -> List[schema.Model]:
    if limit > 100:
        limit = 100
    stmt = (
        select(model.Model)
        .where(
            model.Model.status == status,
            model.Model.user_id == user_id,
        )
        .limit(limit=limit)
        .offset(offset=offset)
    )

    ret: List[schema.Model] = []
    result = await session.execute(stmt)
    for m in result.scalars():
        ret.append(schema.Model(**m.__dict__))

    return ret


async def create_model_from_build(
    session: AsyncSession, build: schema.Build
) -> schema.Model:
    new_model = model.Model(
        **{
            "github_username": build.github_username,
            "repository": build.repository,
            "branch": build.branch,
            "commit": build.commit,
            "notebook": build.notebook,
            "user_id": build.user_id,
            "status": schema.ModelStatus.Draft,
        }
    )
    session.add(new_model)
    await session.commit()
    return schema.Model(**new_model.__dict__)


async def update_model(
    session: AsyncSession, model_id: str, update_values: Dict
) -> bool:
    stmt = (
        update(model.Model)
        .where(
            model.Model.id == str(model_id),
        )
        .values(update_values)
        .execution_options(synchronize_session="fetch")
    )

    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount == 1


async def create_run(
    session: AsyncSession,
    user_id: str,
    run_id: str,
    input_json: dict,
    output_json: dict,
    model_id: str,
    duration_ms: int,
    build_id: str,
) -> schema.Run:
    run = model.Run(
        **{
            "id": run_id,
            "user_id": user_id,
            "input_json": input_json,
            "output_json": output_json,
            "model_id": model_id,
            "duration_ms": duration_ms,
            "build_id": build_id,
        }
    )
    session.add(run)
    await session.commit()
    return schema.Run(**run.__dict__)


async def get_runs(
    session: AsyncSession,
    model_id: str,
    build_id: str,
    user_id: str,
    offset: int = 0,
    limit: int = 10,
) -> List[schema.Run]:
    if limit > 100:
        limit = 100

    where_list = []
    if model_id != None:
        where_list.append(model.Run.model_id == model_id)

    if build_id != None:
        where_list.append(model.Run.build_id == build_id)

    if user_id != None:
        where_list.append(model.Run.user_id == user_id)

    stmt = select(model.Run).where(*where_list).limit(limit=limit).offset(offset=offset)

    ret: List[schema.Run] = []
    result = await session.execute(stmt)
    for m in result.scalars():
        run: schema.Run = schema.Run(**m.__dict__)
        ret.append(run)

    return ret


async def get_run_by_id(
    session: AsyncSession,
    run_id: str,
) -> Optional[schema.Run]:
    stmt = select(model.Run).where(
        model.Run.id == run_id,
    )

    result = await session.execute(stmt)
    for m in result.scalars():
        return schema.Run(**m.__dict__)

    return None
