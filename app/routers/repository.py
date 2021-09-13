from app.helpers.api_helper import ExceptionRoute
from app.db.database import get_session
from app.auth.auth_bearer import JWTBearer
from typing import Coroutine
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import github
import sys
import base64
from pathlib import Path
from app.helpers.logger import get_log

from app.helpers.settings import settings
from app.db import schema
from app.db import crud

from app.helpers.asyncwrapper import async_wrap

router = APIRouter(route_class=ExceptionRoute, prefix="/repository", tags=["github"])


@router.get("/{github_username}", response_model=List[schema.Repository])
async def get_repos(
    github_username: str,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
) -> list:
    user: schema.User = await crud.get_user(session=session, user_id=token.user_id)

    try:
        g = github.Github(user.github_token)
        user = await async_wrap(g.get_user)(github_username)
        repos = await async_wrap(user.get_repos)()
        repos_list = []
        for repo in repos:
            if repo.private == True:
                continue

            repo_schema = schema.Repository(
                full_name=repo.full_name,
                name=repo.name,
                id=repo.id,
                default_branch=repo.default_branch,
                private=repo.private,
            )
            repos_list.append(repo_schema)
        return repos_list
    except github.GithubException as e:
        message = str(sys.exc_info()[1])
        get_log(name=__name__).error(message, exc_info=True)

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )


@router.get(
    "/{github_username}/{repo_name}/branches", response_model=List[schema.Branch]
)
async def get_branches(
    github_username: str,
    repo_name: str,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):

    user: schema.User = await crud.get_user(session=session, user_id=token.user_id)

    try:
        g = github.Github(user.github_token)
        repo = await async_wrap(g.get_repo)(f"{github_username}/{repo_name}")
        branches = await async_wrap(repo.get_branches)()
        branch_names = [
            schema.Branch(name=branch.name, commit=branch.commit.sha)
            for branch in branches
        ]
        return branch_names
    except github.GithubException as e:
        message = str(sys.exc_info()[1])
        get_log(name=__name__).error(message, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found"
        )


@router.get(
    "/{github_username}/{repo_name}/{branch_name}/notebooks",
    response_model=List[schema.Notebook],
)
async def get_notebooks(
    github_username: str,
    repo_name: str,
    branch_name: str,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    user: schema.User = await crud.get_user(session=session, user_id=token.user_id)
    g = github.Github(user.github_token)
    repo = await async_wrap(g.get_repo)(f"{github_username}/{repo_name}")
    contents = repo.get_contents("", ref=branch_name)
    nbs = []
    while contents:
        file_content = contents.pop(0)
        if file_content.type == "dir":
            contents.extend(repo.get_contents(file_content.path, ref=branch_name))
        elif Path(file_content.path).suffix == ".ipynb":
            nbs.append(file_content)

    return [
        schema.Notebook(name=nbs[i].path, size=nbs[i].size)
        for i in range(0, len(nbs), 1)
    ]


@router.get(
    "/{github_username}/{repo_name}/{branch_name}/{notebook_path}",
    response_model=schema.Notebook,
)
async def get_notebook(
    github_username: str,
    repo_name: str,
    branch_name: str,
    notebook_path: str,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    try:
        user: schema.User = await crud.get_user(session=session, user_id=token.user_id)
        g = github.Github(user.github_token)
        repo = await async_wrap(g.get_repo)(f"{github_username}/{repo_name}")
        notebook_path = notebook_path.replace("|", "/")
        contents = repo.get_contents(notebook_path, ref=branch_name)
        file_data = base64.b64decode(contents.content)

        notebook: schema.Notebook = schema.Notebook(
            name=notebook_path, contents=file_data
        )
        return notebook
    except github.GithubException as e:
        if e.status == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Notebook not found"
            )

        if e.status == status.HTTP_403_FORBIDDEN:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Notebook needs to be 1MB or less.",
            )


@router.get(
    "/{github_username}/{repo_name}/{branch_name}/{notebook_path}/check",
    response_model=schema.Notebook,
)
async def check_notebook(
    github_username: str,
    repo_name: str,
    branch_name: str,
    notebook_path: str,
    token: schema.Token = Depends(JWTBearer()),
    session: AsyncSession = Depends(get_session),
):
    notebook: schema.Notebook = await get_notebook(
        github_username=github_username,
        repo_name=repo_name,
        branch_name=branch_name,
        notebook_path=notebook_path,
        token=token,
        session=session,
    )

    # check for pytorch or ts
    is_pytorch = notebook.contents.find("import torch") >= 0
    is_tensorflow = notebook.contents.find("import tensorflow") >= 0

    # download model
    if notebook.contents.find("torch.hub.load") >= 0:
        if notebook.contents.find("torch.hub.set_dir") == -1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="For model download, torch.hub requires torch.hub.set_dir",
            )
    elif notebook.contents.find("!wget -P") == -1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="For model download, please use !wget -P",
        )

    # check has api decorators
    if notebook.contents.find("from inference_params.inference_params") == -1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inference_params reference missing",
        )

    if notebook.contents.find("@inference_predict") == -1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inference_params function decorator missing",
        )
