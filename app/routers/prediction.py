import sys
from typing import Optional

from fastapi import BackgroundTasks
from fastapi.param_functions import Body
from sqlalchemy.sql.functions import user
from app.helpers.boto_helper import invoke_lambda_function
from app.auth.auth_bearer import OptionalJWTBearer
from app.helpers.api_helper import ExceptionRoute

from fastapi.exceptions import HTTPException
from app.db.database import get_session
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import copy
import uuid
from pathlib import Path
from app.helpers.settings import settings
from app.db import schema
from app.db import crud

from app.helpers.logger import get_log

router = APIRouter(
    route_class=ExceptionRoute, prefix="/prediction", tags=["prediction"]
)


async def update_build_lastrun(
    user_id: Optional[str],
    github_username: Optional[str],
    run_id: str,
    model_id: str,
    build_id: str,
    input_json: dict,
    output_json: dict,
    duration_ms: int,
    session: AsyncSession,
):
    # last_run = datetime.now()
    last_run = datetime.now(timezone.utc)
    await crud.update_build(
        session=session,
        build_id=build_id,
        update_values={"last_run": last_run},
    )

    for key, value in input_json.items():
        if f"https://{settings.AWS_REQUESTS_LOG_BUCKET}" in value:
            s3_uri = (
                input_json["image input"]
                .split("?")[0]
                .replace(".s3.amazonaws.com", "")
                .replace("https://", "s3://")
            )
            input_json[key] = s3_uri

    await crud.create_run(
        session=session,
        user_id=user_id,
        github_username=github_username,
        run_id=run_id,
        input_json=input_json,
        output_json=output_json,
        build_id=build_id,
        duration_ms=duration_ms,
        model_id=model_id,
    )


@router.post("/{model_id}", response_model=schema.Run)
async def create(
    model_id: str,
    background_tasks: BackgroundTasks,
    run_id: str,
    payload: dict = Body(...),
    token: Optional[schema.Token] = Depends(OptionalJWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    user = None
    if token != None:
        user: schema.User = await crud.get_user(session=session, user_id=token.user_id)

    model: schema.Model = await crud.get_model_by_id(session=session, model_id=model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    if not run_id:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        val = uuid.UUID(run_id, version=1)
    except ValueError:
        raise HTTPException(status_code=404, detail="Run not valid")

    existing_run: schema.Run = await crud.get_run_by_id(session=session, run_id=run_id)
    if existing_run != None:
        raise HTTPException(status_code=404, detail="Run invalid")

    input_json = copy.deepcopy(payload)

    input_json["request_id"] = f"{model.active_build_id}/{run_id}"
    input_json["output_bucket_name"] = settings.AWS_REQUESTS_LOG_BUCKET
    function_params = {"body": input_json}

    function_name: str = model.active_build.lambda_function_arn
    try:
        result, duration_ms = await invoke_lambda_function(
            function_name=function_name, function_params=function_params
        )
    except:
        duration_ms = 0
        result = {"error": str(sys.exc_info()[1]).split("\r\n")[0]}

    background_tasks.add_task(
        update_build_lastrun,
        user_id=str(user.id) if user else None,
        github_username=user.github_username if user else None,
        run_id=run_id,
        model_id=str(model.id),
        build_id=model.active_build_id,
        input_json=payload,
        output_json=result,
        duration_ms=duration_ms,
        session=session,
    )

    output_json = copy.deepcopy(result)
    input_json = copy.deepcopy(payload)

    run: schema.Run = schema.Run(
        id=run_id,
        user_id=str(user.id) if user else None,
        github_username=user.github_username if user else None,
        input_json=input_json,
        output_json=output_json,
        build_id=model.active_build_id,
        model_id=model_id,
        duration_ms=duration_ms,
        created_at=datetime.now(timezone.utc),
    )

    try:
        get_log(name=__name__).debug(f"{function_name} adding_signed_urls")
        run.add_signed_urls()
        get_log(name=__name__).debug(f"{function_name} finished adding_signed_urls")
    except:
        message = str(sys.exc_info()[1])
        get_log(name=__name__).error(str(message), exc_info=True)
        raise

    # run.add_signed_urls()
    return run
