from app.helpers.boto_helper import read_string_from_s3
from app.helpers.api_helper import ExceptionRoute

from typing import Dict, List
from fastapi.exceptions import HTTPException
from sqlalchemy.sql.functions import mode
from app.db.database import get_session
from app.auth.auth_bearer import JWTBearer
from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.helpers.settings import settings

from app.db import schema
from app.db import crud

from app.helpers.logger import get_log
from app.routers.repository import get_latest_commit

router = APIRouter(route_class=ExceptionRoute, prefix="/build", tags=["build"])


@router.post("/", response_model=schema.Build)
async def create_build(
    build: schema.Build = Body(...),
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    get_log(name=__name__).info(f"Creating build for ${build}")
    user: schema.User = await crud.get_user(session=session, user_id=token.user_id)
    build.user_id = str(user.id)
    build.notebook = build.notebook.replace("|", "/")
    model: schema.Model = await crud.get_model_from_build(session=session, build=build)
    if model == None:
        model = await crud.create_model_from_build(session=session, build=build)
    else:
        running_builds: List[schema.Build] = await crud.get_build(
            session=session,
            model_id=str(model.id),
            user_id=str(user.id),
            github_username=build.github_username,
            repository=build.repository,
            notebook=build.notebook,
            commit=build.commit,
            status=schema.BuildStatus.Started,
        )
        if len(running_builds) > 0:
            return running_builds[0]

    build.model_id = str(model.id)

    if build.commit == None or build.commit == "":
        new_commit: str = await get_latest_commit(user=user, build=build)
        build.commit = new_commit

    build = await crud.create_build(session=session, build=build)

    return build


@router.get("/log/{build_id}", response_model=str)
async def get_build_log(
    build_id: str,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    build: schema.Build = await crud.get_build_by_id(session=session, build_id=build_id)
    if build.build_log != None:
        log_str = await read_string_from_s3(s3_uri=build.build_log)
        return log_str
    return ""


@router.get("/{build_id}", response_model=schema.Build)
async def get_build(build_id: str, session: AsyncSession = Depends(get_session)):
    build: schema.Build = await crud.get_build_by_id(session=session, build_id=build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    return build
