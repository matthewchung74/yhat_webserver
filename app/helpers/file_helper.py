from enum import Enum
from typing import List, cast
import aio_pika
from aio_pika.exchange import Exchange
from aio_pika.robust_channel import RobustChannel
from dotenv.main import resolve_variables
from app.helpers.logger import get_log
import asyncio
import os
from yhat_params.yhat_tools import default_image, FieldType
from app.helpers.settings import settings


class BuilderException(Exception):
    def __init__(self, message: str, build_id: str):
        self.message = message
        self.build_id = build_id

    def __str__(self):
        return f"build_id:{self.build_id} message: {self.message}"


class CancelledException(Exception):
    def __init__(self, build_id: str):
        self.build_id = build_id

    def __str__(self):
        return f"build_id:{self.build_id} message: cancelled"


STARTING_BUILD_FOR = "STARTING BUILD FOR"
STARTING_DOCKER_BUILD = "STARTING DOCKER BUILD"
STARTING_FUNCTION_TESTING = "STARTING FUNCTION TESTING"
PUSHING_DOCKER_TO_AWS = "PUSHING DOCKER TO AWS"
TESTING_IN_CLOUD = "TESTING IN CLOUD"
FINISHED_BUILD = "FINISHED BUILD"
CANCELLED_BUILD = "CANCELLED BUILD"


def sample_params_from_input_json(params: dict):
    new_params = {}
    for (param_key, param_value) in params.items():
        if param_value == FieldType.Text:
            new_params[param_key] = "sample text input, prediction score will be bad"
        # elif param_value == FieldType.OpenCV:
        #     new_params[param_key] = default_image
        elif param_value == FieldType.PIL:
            new_params[param_key] = default_image
    return new_params


def cancel_if_needed(build_id: str) -> bool:
    cancel_file = f"/tmp/{build_id}/cancel.txt"
    if os.path.isfile(cancel_file):
        raise CancelledException(build_id=build_id)

    return False


def delete_cancel_if_needed(build_id: str):
    cancel_file = f"/tmp/{build_id}/cancel.txt"
    try:
        if os.path.isfile(cancel_file):
            os.remove(cancel_file)
    except:
        pass
