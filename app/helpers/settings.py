from app.helpers.asyncwrapper import async_wrap
import os
from typing import Any, Dict, Optional
import boto3
import json

from pydantic import BaseSettings


def load():
    PARAM_STORE = os.getenv("PARAM_STORE")
    ssm_client = None
    if os.getenv("AWS_ACCESS_KEY") == None:
        ssm_client = boto3.client("ssm")
    else:
        ssm_client = boto3.client(
            "ssm",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("AWS_SECRET_KEY"),
            region_name=os.getenv("AWS_REGION_NAME"),
        )

    raw_parameters = ssm_client.get_parameter(Name=PARAM_STORE, WithDecryption=True)
    raw_parameters = raw_parameters["Parameter"]["Value"]
    return json.loads(raw_parameters)


settings = None


async def load_settings_async():
    parameters = await async_wrap(load)()
    global settings
    settings = Settings(**parameters)


class Settings(BaseSettings):
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24
    SQLALCHEMY_DATABASE_URI: str
    SQLALCHEMY_DATABASE_SSL = False
    SQLALCHEMY_DATABASE_MAX_POOL = 20

    JWT_SECRET: str
    JWT_ALGORITHM: str

    GITHUB_OAUTH_URL: str
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_TEST_TOKEN: Optional[str]
    RABBIT_HOST_API: str
    RABBIT_HOST_BUILDER: str
    RABBIT_START_QUEUE_API: str
    RABBIT_START_QUEUE_BUILDER: str
    RABBIT_CANCEL_QUEUE_API: str
    RABBIT_CANCEL_QUEUE_BUILDER: str

    AWS_ACCESS_KEY: str
    AWS_SECRET_KEY: str
    AWS_ACCOUNT_ID: str
    ECR_REPOSITORY_NAME: str
    AWS_BUILD_LOG_BUCKET: str
    AWS_REQUESTS_LOG_BUCKET: str
    DOCKER_AWS_ACCESS_KEY: str
    DOCKER_AWS_SECRET_KEY: str
    DOCKER_AWS_IAM: str
    AWS_REGION_NAME: str
    LAMBDA_DEFAULT_MEMORY: str
    SENDER_EMAIL: str
    WEBSITE_URL: str
    TEST_ALL_MODELS: bool


parameters = load()
settings = Settings(**parameters)
