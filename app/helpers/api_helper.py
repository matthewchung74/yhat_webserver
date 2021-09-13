import time
from typing import Callable
import sys

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute
from app.helpers.logger import get_log


class ExceptionRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                before = time.time()
                response: Response = await original_route_handler(request)
                duration = time.time() - before
                response.headers["X-Response-Time"] = str(duration)
                return response
            except Exception as e:
                get_log(name=__name__).info(f"in custom_route_handler exception")
                message = str(sys.exc_info()[1])
                get_log(name=__name__).error(message, exc_info=True)
                raise e

        return custom_route_handler
