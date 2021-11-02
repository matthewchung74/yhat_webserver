import asyncio
import functools
from pathlib import Path
import boto3
import sys
import os

from botocore.exceptions import ClientError, ReadTimeoutError
from app.helpers.asyncwrapper import async_wrap
import json

from app.helpers.settings import settings
from app.helpers.logger import get_log

import boto3


def get_ecr_private_client():
    if settings.AWS_ACCESS_KEY == None:
        return boto3.client(
            "ecr",
            region_name=settings.AWS_REGION_NAME,
        )
    else:
        return boto3.client(
            "ecr",
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION_NAME,
        )


def get_ecr_public_client():
    if settings.AWS_ACCESS_KEY == None:
        return boto3.client(
            "ecr-public",
            region_name="us-east-1",
        )
    else:
        return boto3.client(
            "ecr-public",
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name="us-east-1",
        )


def get_s3_client():
    if settings.AWS_ACCESS_KEY == None:
        return boto3.resource("s3", region_name=settings.AWS_REGION_NAME)
    else:
        return boto3.resource(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION_NAME,
        )


def get_lambda_client():
    if settings.AWS_ACCESS_KEY == None:
        return boto3.client(
            "lambda",
            region_name=settings.AWS_REGION_NAME,
        )
    else:
        return boto3.client(
            "lambda",
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION_NAME,
        )


def get_ses_client():
    if settings.AWS_ACCESS_KEY == None:
        return boto3.client(
            "ses",
            region_name=settings.AWS_REGION_NAME,
        )
    else:
        return boto3.client(
            "ses",
            aws_access_key_id=settings.AWS_ACCESS_KEY,
            aws_secret_access_key=settings.AWS_SECRET_KEY,
            region_name=settings.AWS_REGION_NAME,
        )


async def write_file_to_s3(src: str, dest: str, bucket: str, alreadyTried=False):
    try:
        s3_client = get_s3_client()
        response = await async_wrap(s3_client.meta.client.upload_file)(
            str(src), bucket, str(dest)
        )
        return response
    except Exception as e:
        if alreadyTried:
            raise
        if str(type(e)) == "<class 'botocore.errorfactory.NoSuchBucket'>":
            await async_wrap(s3_client.create_bucket)(
                Bucket=bucket,
                CreateBucketConfiguration={
                    "LocationConstraint": settings.AWS_REGION_NAME
                },
            )
            await write_file_to_s3(src=src, dest=dest, bucket=bucket, alreadyTried=True)


async def write_string_to_s3(contents: str, s3_uri: str, alreadyTried=False):
    try:
        s3_client = get_s3_client()
        bucket = Path(s3_uri).parts[1]
        key = "/".join(list(Path(s3_uri).parts[2:]))
        s3_obj = await async_wrap(s3_client.Object)(bucket, key)
        await async_wrap(s3_obj.put)(Body=contents)
    except Exception as e:
        if alreadyTried:
            raise
        if str(type(e)) == "<class 'botocore.errorfactory.NoSuchBucket'>":
            # async_create: Coroutine = async_wrap(s3_client.create_bucket)
            await async_wrap(s3_client.create_bucket)(
                Bucket=bucket,
                CreateBucketConfiguration={
                    "LocationConstraint": settings.AWS_REGION_NAME
                },
            )
            await write_string_to_s3(
                contents=contents, s3_uri=s3_uri, alreadyTried=True
            )


async def read_string_from_s3(s3_uri: str, alreadyTried=False):
    try:
        s3_client = get_s3_client()
        bucket = Path(s3_uri).parts[1]
        key = "/".join(list(Path(s3_uri).parts[2:]))
        # async_s3: Coroutine = async_wrap(s3_client.Object)
        s3_obj = await async_wrap(s3_client.Object)(bucket, key)
        # async_get: Coroutine = async_wrap(s3_obj.get)
        s3_stream = await async_wrap(s3_obj.get)()
        return s3_stream["Body"].read().decode()
    except Exception as e:
        if alreadyTried:
            raise
        if str(type(e)) == "<class 'botocore.errorfactory.NoSuchBucket'>":
            # async_create: Coroutine = async_wrap(s3_client.create_bucket)
            await async_wrap(s3_client.create_bucket)(
                Bucket=bucket,
                CreateBucketConfiguration={
                    "LocationConstraint": settings.AWS_REGION_NAME
                },
            )
            await read_string_from_s3(s3_uri=s3_uri, alreadyTried=True)


async def invoke_lambda_function(
    function_name, function_params, alreadyTried=False
) -> tuple:
    try:
        lambda_client = get_lambda_client()
        invoke_partial = functools.partial(
            lambda_client.invoke,
            FunctionName=function_name,
            Payload=json.dumps(function_params).encode(),
        )
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, invoke_partial)
        res_json = json.loads(response["Payload"].read().decode("utf-8"))
        if "errorMessage" in res_json:
            raise Exception(
                res_json["errorMessage"] + "\r\n" + "\r\n".join(res_json["stackTrace"])
            )

        body_json = json.loads(res_json["body"])
        duration_ms = int(body_json["duration ms"] * 1000)
        result_json = json.loads(body_json["result"])
        return result_json, duration_ms
    except (ClientError, ReadTimeoutError) as e:
        if alreadyTried:
            message = str(sys.exc_info()[1])
            get_log(name=__name__).error(str(message), exc_info=True)
            raise
        else:
            get_log(name=__name__).exception(
                "Couldn't invoke function %s, trying again.", function_name
            )

            await invoke_lambda_function(
                function_name=function_name,
                function_params=function_params,
                alreadyTried=True,
            )


def create_presigned_url(bucket_name, object_name, expiration=604800):
    """Generate a presigned URL to share an S3 object

    :param bucket_name: string
    :param object_name: string
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Presigned URL as string. If error, returns None.
    """

    # Generate a presigned URL for the S3 object
    s3_client = get_s3_client().meta.client
    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": object_name},
            ExpiresIn=expiration,
        )
    except ClientError as e:
        get_log(name=__name__).exception("Error creating signed url")
        raise

    # The response contains the presigned URL
    return response


# https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html
def create_presigned_post(
    bucket_name, object_name, fields=None, conditions=None, expiration=3600
):
    """Generate a presigned URL S3 POST request to upload a file

    :param bucket_name: string
    :param object_name: string
    :param fields: Dictionary of prefilled form fields
    :param conditions: List of conditions to include in the policy
    :param expiration: Time in seconds for the presigned URL to remain valid
    :return: Dictionary with the following keys:
        url: URL to post to
        fields: Dictionary of form fields and values to submit with the POST
    :return: None if error.
    """

    s3_client = get_s3_client().meta.client
    try:
        response = s3_client.generate_presigned_post(
            bucket_name,
            object_name,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=expiration,
        )
    except ClientError as e:
        get_log(name=__name__).exception("Error creating signed url")
        raise

    return response


async def send_email(to_address: str, sender: str, subject: str, text: str, html: str):
    s3_client = get_ses_client()
    try:
        response = await async_wrap(s3_client.send_email)(
            Destination={
                "ToAddresses": [to_address],
            },
            Message={
                "Body": {
                    "Html": {
                        "Charset": "UTF-8",
                        "Data": html,
                        # 'Data': 'This message body contains HTML formatting. It can, for example, contain links like this one: <a class="ulink" href="http://docs.aws.amazon.com/ses/latest/DeveloperGuide" target="_blank">Amazon SES Developer Guide</a>.',
                    },
                    "Text": {
                        "Charset": "UTF-8",
                        "Data": text,
                        # 'Data': 'This is the message body in text format.',
                    },
                },
                "Subject": {
                    "Charset": "UTF-8",
                    "Data": subject,
                },
            },
            Source=sender,
            ReplyToAddresses=[sender],
        )
    except ClientError as e:
        get_log(name=__name__).exception("Error sending email")
        raise
