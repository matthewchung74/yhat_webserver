# based on
# https://stackoverflow.com/questions/45839549/docker-python-api-tagging-containers

from typing import Callable, Coroutine, Generator, Tuple
from app.helpers.logger import get_log

import base64
from botocore.exceptions import ClientError
import shutil
from nbconvert import PythonExporter
import nbformat
from urllib.request import urlopen
from jinja2 import DictLoader

import boto3
import docker
import json
import time
import requests
from pathlib import Path
import sys
import os

from yhat_params.yhat_tools import FieldType

from app.helpers.file_helper import BuilderException, sample_params_from_input_json
from app.helpers.settings import settings

import logging

logging.getLogger("docker").setLevel(logging.DEBUG)


# warning caused by
# https://github.com/jupyter/nbconvert/issues/1568
def convert_to_py(nb_path: str) -> tuple:
    response = urlopen(f"file://{nb_path}").read().decode()
    nb = nbformat.reads(response, as_version=4)

    dl = DictLoader(
        {
            "cleanup": """
{%- extends 'null.j2' -%}

## set to python3
{%- block header -%}
#!/usr/bin/env python3
# coding: utf-8
{% endblock header %}

## remove cell counts entirely
{% block in_prompt %}
{% if resources.global_content_filter.include_input_prompt -%}
{% endif %}
{% endblock in_prompt %}

## remove markdown cells entirely
{% block markdowncell %}
{% endblock markdowncell %}

{% block input %}
{{ cell.source | ipython2python }}
{% endblock input %}


## remove magic statement completely
{% block codecell %}
{{'' if "get_ipython" in super() else super() }}
{% endblock codecell%}
    """
        }
    )

    python_exporter = PythonExporter(extra_loaders=[dl], template_file="cleanup")
    (body, resources) = python_exporter.from_notebook_node(nb)

    script_path = nb_path.replace("ipynb", "py")
    with open(script_path, "w") as file_out:
        file_out.write(body)

    return nb_path, script_path


def copy_to_app(script_nb: str, script_py: str, app_dir: Path, tmp_dir: Path):
    shutil.copy(script_nb, app_dir / "inference.ipynb")
    shutil.copy(script_py, app_dir / "inference.py")
    template_path = "app/service/builder_server/lambda_template"
    docker_path = "app/service/builder_server/docker_template"
    shutil.copy(f"{template_path}/app.py", app_dir / "app.py")
    shutil.copy(f"{template_path}/env", app_dir / ".env")
    shutil.copytree(f"{template_path}/docker_vscode/", app_dir / ".vscode")
    shutil.copy(f"{docker_path}/Dockerfile", tmp_dir / "Dockerfile")


def login_aws(
    docker_client: docker.APIClient,
    ecr_private_client: boto3.client,
    ecr_public_client: boto3.client,
    aws_account_id: str,
    build_id: str,
) -> Tuple[str, str, str]:
    # private ecr
    response = ecr_private_client.get_authorization_token(registryIds=[aws_account_id])
    username, password = (
        base64.b64decode(response["authorizationData"][0]["authorizationToken"])
        .decode()
        .split(":")
    )
    registry = response["authorizationData"][0]["proxyEndpoint"]
    response = docker_client.login(username, password, registry=registry)
    if response["Status"] != "Login Succeeded":
        raise BuilderException("Login to AWS failed", build_id=build_id)

    # public ecr
    # if continue to get login problems, try command line
    # aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/c6h1o1s4
    response = ecr_public_client.get_authorization_token()
    usr, pwd = (
        base64.b64decode(response["authorizationData"]["authorizationToken"])
        .decode()
        .split(":")
    )
    response = docker_client.login(
        usr, pwd, registry="https://public.ecr.aws/c6h1o1s4", reauth=True
    )
    if response["Status"] != "Login Succeeded":
        raise BuilderException("Login to AWS failed", build_id=build_id)

    return username, password, registry


# def pull_base(
#     docker_client: docker.APIClient,
# ):
#     docker_client.pull(
#         "public.ecr.aws/c6h1o1s4/inference_lambda_public:base_pytorch",
#         stream=False,
#         decode=True,
#     )


def convert_to_docker(
    docker_client: docker.APIClient,
    tag: str,
    tmp_dir: str,
    build_id: str,
    cancel_if_needed: Callable,
):
    foundStart = None
    foundEnd = None

    for payload in docker_client.build(
        rm=True, tag=tag, path=tmp_dir, nocache=True, forcerm=False
    ):
        for segment in payload.decode().split("\r\n"):
            cancel_if_needed()
            line = segment.strip()
            if line:
                try:
                    # get_log(name=__file__).info(f"convert_to_docker {line}")
                    line_payload = json.loads(line)
                    foundStart = None
                    foundEnd = None
                except ValueError as ex:
                    if str(type(ex)) == "<class 'json.decoder.JSONDecodeError'>":
                        if line.startswith("{"):
                            foundStart = line
                        if line.endswith("}"):
                            foundEnd = line
                        if foundStart != None and foundEnd != None:
                            try:
                                line_payload = json.loads(f"{foundStart}{foundEnd}")
                            except:
                                continue
                        else:
                            continue
                    else:
                        raise BuilderException(
                            message="Could not decipher payload from API: " + str(ex),
                            build_id=build_id,
                        )

                if line_payload:
                    if "errorDetail" in line_payload:
                        yield {
                            "message": line_payload["errorDetail"]["message"],
                            "type": "error",
                        }
                        return
                    elif "stream" in line_payload:
                        yield {"message": line_payload["stream"], "type": "message"}


def inspect_image(docker_client: docker.APIClient, tag: str, build_id: str):
    inspection = docker_client.inspect_image(tag)
    get_log(name=__name__).info(
        f"Docker image size {round(inspection['Size']/1000000000, 2)} GB"
    )
    if inspection["Size"] > 10000000000:
        raise BuilderException(
            message=f"docker image size {inspection['Size']} exceeds max of 10G",
            build_id=build_id,
        )
    return inspection["Size"]


def tag_image(docker_client: docker.APIClient, tag: str, image_uri: str):
    try:
        docker_client.remove_image(image_uri, force=True)
    except Exception as e:
        if str(type(e)) == "<class 'docker.errors.ImageNotFound'>":
            pass
        else:
            raise

    docker_client.tag(tag, image_uri)


def prune_images(docker_client: docker.APIClient, docker_image_id: str):
    try:
        docker_client.remove_image(docker_image_id, force=True)
        docker_client.prune_images(filters={"dangling": 1, "until": "2h"})
    except docker.errors.APIError:
        pass


def push_to_aws(
    docker_client: docker.APIClient,
    image_uri: str,
    auth_config_payload: str,
    cancel_if_needed: Callable,
) -> Generator:
    for line in docker_client.push(
        image_uri, stream=True, decode=True, auth_config=auth_config_payload
    ):
        cancel_if_needed()
        get_log(name=__file__).info(f"convert_to_docker {line}")
        yield "."


def test_build_docker(
    docker_client: docker.APIClient,
    image_uri: str,
    docker_tag: str,
    build_id: str,
    build_index: int,
):
    client = None
    container = None
    try:
        # stop all running containers
        client = docker.from_env()
        containers = client.containers.list(all=True, ignore_removed=True)
        for container in containers:
            if len(container.image.tags) > 0 and container.image.tags[0] == docker_tag:
                container.kill()

        def run_container():
            # start container
            # docker run -p 9000:8080 {tag}
            port = 9000 + build_index
            container = client.containers.run(
                image=docker_tag,
                ports={"8080/tcp": port},
                environment={
                    "AWS_ACCESS_KEY": settings.DOCKER_AWS_ACCESS_KEY,
                    "AWS_SECRET_KEY": settings.DOCKER_AWS_SECRET_KEY,
                    "AWS_REGION_NAME": settings.AWS_REGION_NAME,
                    "AWS_REQUEST_BUCKET": settings.AWS_REQUESTS_LOG_BUCKET,
                },
                detach=True,
                auto_remove=True,
                mem_limit=f"{settings.LAMBDA_DEFAULT_MEMORY}m",
            )

            time.sleep(0.2)
            return container, port

        try:
            container, port = run_container()
        except Exception:
            if "port is already allocated" in str(sys.exc_info()[1]):
                container, port = run_container()
            else:
                yield {
                    "message": "Error running local docker container for testing",
                    "type": "error",
                }
                return

        yield {
            "message": "Running local docker container for testing",
            "type": "message",
        }

        # same as curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"body":{"text input":"movie was awful"}}'
        # used for local lambda test
        url = f"http://localhost:{port}/2015-03-31/functions/function/invocations"
        response = requests.post(
            url, data=json.dumps({"body": {"get_inference_input_json": 1}})
        )

        if "errorMessage" in response.json():
            stack_trace = "".join(response.json()["stackTrace"])
            stack_trace = stack_trace.replace("\n", "\r\n")
            error_message = response.json()["errorMessage"].replace("\n", "\r\n")
            raise BuilderException(
                message=error_message + stack_trace,
                build_id=build_id,
            )

        input_json = json.loads(json.loads(response.json()["body"])["result"])
        yield {
            "message": f"Found input json {json.dumps(input_json)}",
            "type": "message",
        }
        yield {"message": f"{json.dumps(input_json)}", "type": "input_json"}

        response = requests.post(
            url, data=json.dumps({"body": {"get_inference_output_json": 1}})
        )

        if "errorMessage" in response.json():
            stack_trace = "".join(response.json()["stackTrace"])
            stack_trace = stack_trace.replace("\n", "\r\n")
            error_message = response.json()["errorMessage"].replace("\n", "\r\n")
            raise BuilderException(
                message=error_message + stack_trace,
                build_id=build_id,
            )

        output_json = json.loads(json.loads(response.json()["body"])["result"])
        yield {
            "message": f"Found output json {json.dumps(output_json)}",
            "type": "message",
        }
        yield {"message": f"{json.dumps(output_json)}", "type": "output_json"}

        myobj = sample_params_from_input_json(params=input_json)
        myobj["request_id"] = build_id
        response = requests.post(url, data=json.dumps({"body": myobj}))

        if "errorMessage" in response.json():
            stack_trace = "".join(response.json()["stackTrace"])
            stack_trace = stack_trace.replace("\n", "\r\n")
            error_message = response.json()["errorMessage"].replace("\n", "\r\n")
            raise BuilderException(
                message=error_message + stack_trace,
                build_id=build_id,
            )

        body = json.loads(response.json()["body"])
        result = json.loads(body["result"])

        yield {"message": f"Running predict function", "type": "message"}
        for key in output_json.keys():
            if output_json[key] == FieldType.Text:
                if type(result[key]) != type(""):
                    yield {"message": f"For {key}, expected text", "type": "error"}
                    return
            elif (
                output_json[key]
                == FieldType.PIL
                # and output_json[key] == FieldType.OpenCV
            ):
                if not Path(result[key]).parts[0] in ["http:", "https:", "s3:"]:
                    yield {"message": f"For {key}, expected image", "type": "error"}
                    return

        yield {"message": f"Running predict function success", "type": "message"}

    finally:
        try:
            if container:
                container.remove(force=True)
        except:
            get_log(name=__name__).error(f"builder:{build_id} error", exc_info=True)
            pass
