# import debugpy

# debugpy.listen(5678)
# debugpy.wait_for_client()

import logging
import time
logging.basicConfig(level = logging.INFO)
logger = logging.getLogger()

import os
import json
import copy
from yhat_params.yhat_tools import (
    convert_input_params,
    convert_output_params,
)

before_inference_load = time.time()
from inference import predict
logger.info(f"from inference ${time.time() - before_inference_load}")

if os.path.isfile(".env"):
    from dotenv import load_dotenv
    load_dotenv()


API_KEY = os.getenv("API_KEY")


def handler(event, context):

    if type(event["body"]) is dict:
        body = copy.deepcopy(event["body"])
    else:
        body = copy.deepcopy(json.loads(event["body"]))

    if API_KEY != None and "API_KEY" not in event:
        raise Exception("Missing API_KEY")
    elif API_KEY != None and event["API_KEY"] != os.getenv("API_KEY"):
        raise Exception("Incorrect API_KEY")

    if "request_id" in body:
        request_id = body["request_id"]
        del body["request_id"]
    else:
        request_id = "test_request_id"

    if "output_bucket_name" in body:
        output_bucket_name = body["output_bucket_name"]
        del body["output_bucket_name"]
    else:
        output_bucket_name = None

    # request to get input json
    if "get_inference_input_json" in body:
        with open("/tmp/input.json") as f:
            input_format = json.load(f)
            return {
                "headers": {"Content-Type": "application/json"},
                "statusCode": 200,
                "body": json.dumps(
                    {
                        "message": "input format here",
                        "event": event,
                        "result": json.dumps(input_format),
                    }
                ),
            }

    # request to get output json
    if "get_inference_output_json" in body:
        with open("/tmp/output.json") as f:
            output_format = json.load(f)
            return {
                "headers": {"Content-Type": "application/json"},
                "statusCode": 200,
                "body": json.dumps(
                    {"event": event, "result": json.dumps(output_format)}
                ),
            }

    before_convert_input_params = time.time()

    # convert and check input types before predict
    new_params = convert_input_params(
        params=body, object_prefix=request_id, bucket_name=output_bucket_name
    )

    logger.info(f"convert_input_params ${time.time() - before_convert_input_params}")


    before_predict = time.time()

    # perform prediction
    result, duration = predict(body)

    logger.info(f"predict ${time.time() - before_predict}")

    before_convert_output_params = time.time()

    # convert and check output types before returning to client
    new_result = convert_output_params(
        result=result, object_prefix=request_id, bucket_name=output_bucket_name
    )

    logger.info(f"before_convert_output_params ${time.time() - before_convert_output_params}")

    return {
        "headers": {"Content-Type": "application/json"},
        "statusCode": 200,
        "body": json.dumps(
            {
                "event": event,
                "result": json.dumps(new_result),
                "duration ms": round(duration, 3),
            }
        ),
    }
