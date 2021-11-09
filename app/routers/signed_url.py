from typing import List
from fastapi.exceptions import HTTPException

from fastapi import BackgroundTasks

from app.helpers.boto_helper import (
    create_presigned_post,
)
from app.auth.auth_bearer import JWTBearer
from app.helpers.api_helper import ExceptionRoute

from yhat_params.yhat_tools import FieldType

from app.db.database import get_session
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import json

from app.helpers.settings import settings

from app.db import schema
from app.db import crud

from app.helpers.logger import get_log

router = APIRouter(
    route_class=ExceptionRoute, prefix="/signed_url", tags=["signed_url"]
)


@router.post("/{model_id}", response_model=List[schema.JSONStructure])
async def create(
    model_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    model: schema.Model = await crud.get_model_by_id(session=session, model_id=model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if not model.active_build:
        raise HTTPException(status_code=404, detail="Model Build not found")

    if not run_id:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        val = uuid.UUID(run_id, version=1)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not valid")

    run: schema.Run = await crud.get_run_by_id(session=session, run_id=run_id)
    if run != None:
        raise HTTPException(status_code=404, detail="Run invalid")

    ret = []
    for _, value in model.active_build.input_json.items():
        if FieldType.PIL == value:  # or FieldType.OpenCV == value:
            output = create_presigned_post(
                bucket_name=settings.AWS_REQUESTS_LOG_BUCKET,
                object_name=f"{model.active_build_id}/{run_id}/{str(uuid.uuid1())}.jpg",
            )
            ret.append(output)

    return ret
