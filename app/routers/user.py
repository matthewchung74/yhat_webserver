from app.helpers.api_helper import ExceptionRoute
from uuid import UUID
from fastapi import APIRouter, Response, Body, Depends, HTTPException, status
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

import github

from app.helpers.settings import settings
from app.db import schema
from app.db.database import get_session
from app.db import crud
from app.auth.auth_bearer import JWTBearer
from app.auth.auth_handler import signJWT, signCSRF
from app.helpers.logger import get_log

router = APIRouter(route_class=ExceptionRoute, prefix="/user", tags=["user"])


async def _fetch_github_user(token: str) -> schema.User:
    user_github = github.Github(token).get_user()
    emails = user_github.get_emails()
    if emails == None or len(emails) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid GitHub email"
        )
    email = emails[0].email
    user = schema.GithubUser(
        avatar_url=user_github.avatar_url,
        html_url=user_github.html_url,
        fullname=user_github.name,
        github_id=user_github.id,
        github_username=user_github.login,
        email=email,
        github_token=token,
        type=schema.UserType.GithubVerified,
    )
    return user


async def _fetch_github_access(code: str) -> str:
    async with httpx.AsyncClient() as client:
        data = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
        }
        headers = {"Accept": "application/json"}
        response = await client.post(
            settings.GITHUB_OAUTH_URL, json=data, headers=headers
        )

        if response.status_code != status.HTTP_200_OK:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub code"
            )

        if "error" in response.json():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid GitHub code"
            )

        access_token_github = response.json()["access_token"]
        scope_github = response.json()["scope"]
        if scope_github != "repo,user":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid GitHub permissions",
            )

        return access_token_github


@router.post("/login/github", response_model=schema.Token)
async def user_login_github(
    response: Response,
    github_code: schema.GithubUserLoginSchema = Body(...),
    session: AsyncSession = Depends(get_session),
):
    access_token_github: str = await _fetch_github_access(github_code.code)
    github_user: schema.User = await _fetch_github_user(token=access_token_github)

    user: schema.User = await crud.create_user_from_github(
        session=session, github_user=github_user
    )

    if not await crud.get_has_early_access(session=session, email=user.email):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub permissions",
        )

    jwt_token = signJWT(user)
    csrf_token = signCSRF(user)
    response.set_cookie(
        key="authorization", value=f"Bearer {csrf_token.token}", httponly=True
    )

    return schema.Token(token=jwt_token.token, user_id=user.id)


@router.get("/me", response_model=schema.ProfileUser)
async def get_me(
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    user_id = token.user_id
    user: schema.User = await crud.get_user(session=session, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = schema.ProfileUser(**user.dict())
    return user


@router.get("/{user_id}", response_model=schema.ProfileUser)
async def get_profile(user_id: str, session: AsyncSession = Depends(get_session)):
    user: schema.User = await crud.get_user(session=session, user_id=user_id)
    profile = schema.ProfileUser(**user.dict())
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
