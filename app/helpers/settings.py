import os

from pydantic import BaseSettings


# secret_key = os.getenv("SECRET_KEY") if os.getenv("SECRET_KEY") else "abc"


class Settings(BaseSettings):
    # SECRET_KEY = secret_key
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
    SQLALCHEMY_DATABASE_SSL = False
    SQLALCHEMY_DATABASE_MAX_POOL = 20

    JWT_SECRET = os.getenv("JWT_SECRET") if os.getenv("JWT_SECRET") else "abc"
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM") if os.getenv("JWT_ALGORITHM") else "abc"

    GITHUB_TEST_TOKEN = (
        os.getenv("GITHUB_TEST_TOKEN") if os.getenv("GITHUB_TEST_TOKEN") else "abc"
    )
    GITHUB_OAUTH_URL = (
        os.getenv("GITHUB_OAUTH_URL") if os.getenv("GITHUB_OAUTH_URL") else "abc"
    )
    GITHUB_CLIENT_ID = (
        os.getenv("GITHUB_CLIENT_ID") if os.getenv("GITHUB_CLIENT_ID") else "abc"
    )
    GITHUB_CLIENT_SECRET = (
        os.getenv("GITHUB_CLIENT_SECRET")
        if os.getenv("GITHUB_CLIENT_SECRET")
        else "abc"
    )

    RABBIT_HOST = (
        os.getenv("RABBIT_HOST")
        if os.getenv("RABBIT_HOST")
        else "amqp://guest:guest@localhost/?heartbeat=300&connection_timeout=300000"
    )
    RABBIT_START_QUEUE = (
        os.getenv("RABBIT_START_QUEUE")
        if os.getenv("RABBIT_START_QUEUE")
        else "build_start"
    )
    RABBIT_CANCEL_QUEUE = (
        os.getenv("RABBIT_CANCEL_QUEUE")
        if os.getenv("RABBIT_CANCEL_QUEUE")
        else "build_cancel"
    )

    AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
    AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
    AWS_BUILD_LOG_BUCKET = (
        os.getenv("AWS_BUILD_LOG_BUCKET")
        if os.getenv("AWS_BUILD_LOG_BUCKET")
        else "inference-imagebuilder-logs"
    )
    AWS_REQUESTS_LOG_BUCKET = (
        os.getenv("AWS_REQUESTS_LOG_BUCKET")
        if os.getenv("AWS_REQUESTS_LOG_BUCKET")
        else "inference-requests-logs"
    )
    DOCKER_AWS_ACCESS_KEY = os.getenv("DOCKER_AWS_ACCESS_KEY")
    DOCKER_AWS_SECRET_KEY = os.getenv("DOCKER_AWS_SECRET_KEY")
    DOCKER_AWS_IAM = os.getenv("DOCKER_AWS_IAM")
    AWS_REGION_NAME = os.getenv("AWS_REGION_NAME")
    LAMBDA_DEFAULT_MEMORY = os.getenv("LAMBDA_DEFAULT_MEMORY")
    SENDER_EMAIL = (
        os.getenv("SENDER_EMAIL") if os.getenv("SENDER_EMAIL") else AssertionError()
    )
    WEBSITE_URL = os.getenv("WEBSITE_URL")


settings = Settings()
