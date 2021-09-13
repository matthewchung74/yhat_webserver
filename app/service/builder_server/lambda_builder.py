# based on
# https://docs.aws.amazon.com/code-samples/latest/catalog/python-lambda-boto_client_examples-lambda_basics.py.html

import asyncio
import json
import time
from typing import Callable, Generator
from botocore.exceptions import ClientError
from app.helpers.boto_helper import get_lambda_client
from app.helpers.logger import get_log
from app.helpers.settings import settings


def exponential_retry(func, error_code, *func_args, **func_kwargs):
    sleepy_time = 1
    func_return = None
    while sleepy_time < 33 and func_return is None:
        try:
            yield from func(*func_args, **func_kwargs)
            get_log(name=__name__).info("Ran %s, got %s.", func.__name__, func_return)
        except ClientError as error:
            if error.response["Error"]["Code"] == error_code:
                yield (
                    f"Sleeping for {sleepy_time} to give AWS time to "
                    f"connect resources."
                )
                time.sleep(sleepy_time)
                sleepy_time = sleepy_time * 2
            else:
                raise


def lambda_function_exists(function_name: str):
    try:
        lambda_client = get_lambda_client()
        response = lambda_client.get_function(FunctionName=function_name)
    except ClientError as error:
        if "Function not found" in error.response["Error"]["Message"]:
            return False
    return True


def deploy_lambda(
    function_name: str, image_uri: str, tags: dict, cancel_if_needed: Callable
) -> Generator:
    try:
        lambda_client = get_lambda_client()
        response = lambda_client.create_function(
            FunctionName=function_name,
            Description="",
            Role=settings.DOCKER_AWS_IAM,
            Code={"ImageUri": image_uri},
            Timeout=900,
            MemorySize=int(settings.LAMBDA_DEFAULT_MEMORY),
            PackageType="Image",
            Tags=tags,
            Environment={
                "Variables": {"AWS_REQUEST_BUCKET": "inference-imagebuilder-logs"}
            },
            Publish=True,
        )

        waiter = lambda_client.get_waiter("function_active")

        max_attempts = 300
        for i in range(max_attempts):
            try:
                cancel_if_needed()
                waiter.wait(
                    FunctionName=function_name,
                    WaiterConfig={"Delay": 2, "MaxAttempts": 2},
                )
                yield {"type": "arn", "message": response["FunctionArn"]}
                return
            except Exception as e:
                get_log(name=__file__).info(f"attempt {i} {str(e)}")

                if "Max attempts exceeded" in str(e):
                    yield {"type": "dot", "message": "."}
                    if i == (max_attempts - 1):
                        raise
                elif i > 0 and "Function already exist" in str(e):
                    yield {"type": "arn", "message": response["FunctionArn"]}
                    return
                else:
                    raise
    except ClientError as ce:
        if ce.response["Error"]["Code"] == "ResourceConflictException":
            get_log(name=__name__).exception(
                "Lambda update currently in progress", function_name
            )
            raise
        else:
            get_log(name=__name__).exception(
                "Couldn't create function %s.", function_name
            )
            raise


def update_lambda_function(function_name: str, image_uri: str) -> str:
    try:
        lambda_client = get_lambda_client()
        waiter = lambda_client.get_waiter("function_active")
        waiter.wait(
            FunctionName=function_name,
            Qualifier="$LATEST",
            WaiterConfig={"Delay": 0.1, "MaxAttempts": 1},
        )
    except ClientError as ce:
        get_log(name=__name__).exception(
            f"Caught exception trying to update {function_name}", ce
        )
        raise

    try:
        response = lambda_client.update_function_code(
            FunctionName=function_name, ImageUri=image_uri, Publish=True
        )

        get_log(name=__name__).info(f"Started update lambda function {function_name}.")

        waiter = lambda_client.get_waiter("function_updated")
        waiter.wait(
            FunctionName=function_name,
            Qualifier="$LATEST",
            WaiterConfig={"Delay": 5, "MaxAttempts": 120},
        )

        get_log(name=__name__).info(f"Updated lambda function {function_name}.")
        return response["FunctionArn"]

    except ClientError as ce:
        if ce.response["Error"]["Code"] == "ResourceConflictException":
            get_log(name=__name__).exception(
                "Lambda update currently in progress", function_name
            )
            raise
        else:
            raise


def delete_lambda(function_name):
    try:
        lambda_client = get_lambda_client()
        lambda_client.delete_function(FunctionName=function_name)
    except ClientError:
        get_log(name=__name__).exception("Couldn't delete function %s.", function_name)
        raise


def build(lambda_function_name: str, iam_role_arn: str, image_uri: str, tags: dict):

    lambda_exists = lambda_function_exists(function_name=lambda_function_name)

    function_arn = None
    if lambda_exists:
        delete_lambda(function_name=lambda_function_name)

    function_arn = exponential_retry(
        deploy_lambda,
        "InvalidParameterValueException",
        lambda_function_name,
        iam_role_arn,
        image_uri,
        tags,
    )

    return function_arn
