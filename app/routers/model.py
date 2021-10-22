from app.helpers.api_helper import ExceptionRoute

from typing import Dict, List, Optional
from fastapi.exceptions import HTTPException
from starlette import status
from fastapi import WebSocket
from typer.params import Option
from app.db.database import get_session
from app.auth.auth_bearer import JWTBearer
from fastapi import APIRouter, Depends, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.helpers.settings import settings

from app.db import schema
from app.db import crud

from app.helpers.logger import get_log

router = APIRouter(route_class=ExceptionRoute, prefix="/model", tags=["model"])


@router.get("/", response_model=List[schema.Model])
async def get_models(
    offset: Optional[int] = 0,
    limit: Optional[int] = 10,
    user_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    if user_id == None:
        return await crud.get_models(
            session=session,
            offset=offset,
            limit=limit,
            status=schema.ModelStatus.Public,
        )
    else:
        return await crud.get_models_by_user_id(
            session=session, offset=offset, limit=limit, user_id=user_id
        )


@router.get("/me", response_model=List[schema.Model])
async def get_me(
    status: Optional[schema.ModelStatus] = schema.ModelStatus.Public,
    offset: Optional[int] = 0,
    limit: Optional[int] = 10,
    user_id: Optional[str] = None,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    user_id = str(token.user_id)

    return await crud.get_models_by_user_id(
        session=session, offset=offset, limit=limit, user_id=user_id, status=status
    )


@router.put("/{model_id}", response_model=schema.Model)
async def update_model(
    model_id: str,
    params: dict = Body(...),
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    user_id = str(token.user_id)

    model: schema.Model = await crud.get_model_by_id(session=session, model_id=model_id)
    if model.user_id != user_id:
        raise HTTPException(status_code=404, detail="Model not found.")

    model_dict: dict = {}
    if "title" in params:
        model_dict["title"] = params["title"]
    if "credits" in params:
        model_dict["credits"] = params["credits"]
    if "description" in params:
        model_dict["description"] = params["description"]

    if len(model_dict) > 0:
        await crud.update_model(
            session=session, model_id=model_id, update_values=model_dict
        )

    if "release_notes" in params:
        await crud.update_build(
            session=session,
            build_id=model.active_build_id,
            update_values={"release_notes": params["release_notes"]},
        )

    return await crud.get_model_by_id(session=session, model_id=model_id)


@router.delete("/{model_id}", response_model=schema.Model)
async def delete_model(
    model_id: str,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    user_id = str(token.user_id)

    model: schema.Model = await crud.get_model_by_id(session=session, model_id=model_id)
    if model.id == None:
        raise HTTPException(status_code=404, detail="Model not found.")

    if model.user_id != user_id:
        raise HTTPException(status_code=404, detail="Model not found.")

    await crud.update_model(
        session=session,
        model_id=model_id,
        update_values={"status": schema.ModelStatus.Deleted},
    )

    return await crud.get_model_by_id(session=session, model_id=model_id)


@router.get("/{model_id}", response_model=schema.Model)
async def get_model(model_id: str, session: AsyncSession = Depends(get_session)):
    model: schema.Model = await crud.get_model_by_id(session=session, model_id=model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model
