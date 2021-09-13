from typing import List, Optional
from fastapi import BackgroundTasks
from fastapi.param_functions import Body

from app.auth.auth_bearer import JWTBearer
from app.helpers.api_helper import ExceptionRoute

from fastapi.exceptions import HTTPException
from typer.params import Option
from app.db.database import get_session
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import datetime
import copy
import uuid

from app.helpers.settings import settings

from app.db import schema
from app.db import crud

from app.helpers.logger import get_log

router = APIRouter(route_class=ExceptionRoute, prefix="/run", tags=["run"])


@router.get("/", response_model=List[schema.Run])
async def get_runs(
    offset: Optional[int] = 0,
    limit: Optional[int] = 10,
    model_id: Optional[str] = None,
    build_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    runs: List[schema.Run] = await crud.get_runs(
        session=session,
        offset=offset,
        limit=limit,
        model_id=model_id,
        build_id=build_id,
        user_id=user_id,
    )

    for run in runs:
        run.add_signed_urls()

    return runs
