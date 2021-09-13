from dotenv import load_dotenv

load_dotenv()

from app.helpers.logger import get_log
from fastapi import FastAPI
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.db.database import get_session
from fastapi import Request, Response

from fastapi.middleware.cors import CORSMiddleware
from app.routers import user
from app.routers import repository
from app.routers import build
from app.routers import model
from app.routers import prediction
from app.routers import signed_url
from app.routers import run
from app.service.builder_client import builder_client
from app.db import database

get_log(name=__name__).info(f"Starting API Server")


app = FastAPI()


app.include_router(user.router)
app.include_router(repository.router)
app.include_router(build.router)
app.include_router(model.router)
app.include_router(prediction.router)
app.include_router(signed_url.router)
app.include_router(run.router)


@app.on_event("startup")
async def startup_event():
    await database.init_models()


@app.on_event("shutdown")
async def shutdown_event():
    await database.dispose()


@app.get("/", tags=["root"])
async def read_root() -> dict:
    return {"message": "Welcome to inference."}


@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, session: AsyncSession = Depends(get_session)
):
    await builder_client.start(websocket=websocket, session=session)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:9000",
        "http://inference-app.s3-website-us-west-2.amazonaws.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
