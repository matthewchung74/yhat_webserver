from async_asgi_testclient import TestClient
from requests.models import cookiejar_from_dict
from app.api import app
from app.auth import auth_bearer
from typing import List
from app.db import schema
import urllib

import pytest

from app.helpers.settings import settings
from app.routers import user


@pytest.fixture
async def client():
    async with TestClient(app) as client:
        yield client


@pytest.mark.asyncio
async def test_repository(client, storage):

    # fetch me
    def mock_func(_):
        return 'Bearer', storage['token']

    auth_bearer.get_cookies = mock_func

    headers = {'Accept': 'application/json',
               "Authorization": f"Bearer {storage['token']}"}

    github_username = storage['github_username']
    response = await client.get(f"/repository/{github_username}", headers=headers)
    assert response.status_code == 200
    assert type(response.json()) == type([])
    repos_list: List[schema.Repository] = response.json()
    assert len(repos_list) > 0
    for repo in repos_list:
        assert repo['default_branch'] != None
    storage["repo_name"] = repos_list[0]['name']


@pytest.mark.asyncio
async def test_branch(client, storage):

    # fetch me
    def mock_func(_):
        return 'Bearer', storage['token']

    auth_bearer.get_cookies = mock_func

    headers = {'Accept': 'application/json',
               "Authorization": f"Bearer {storage['token']}"}

    github_username = storage['github_username']
    repo_name = storage['repo_name']
    response = await client.get(f"/repository/{github_username}/{repo_name}/branches", headers=headers)
    assert response.status_code == 200
    assert type(response.json()) == type([])
    branch_list: List[schema.Branch] = response.json()
    assert len(branch_list) > 0
    storage["branch_name"] = branch_list[0]['name']


@pytest.mark.asyncio
async def test_nbs(client, storage):

    # fetch me
    def mock_func(_):
        return 'Bearer', storage['token']

    auth_bearer.get_cookies = mock_func

    headers = {'Accept': 'application/json',
               "Authorization": f"Bearer {storage['token']}"}

    github_username = storage['github_username']
    repo_name = storage['repo_name']
    branch_name = storage['branch_name']
    response = await client.get(f"/repository/{github_username}/{repo_name}/{branch_name}/notebooks", headers=headers)
    assert response.status_code == 200
    assert type(response.json()) == type([])
    notebook_list: List[schema.Notebook] = response.json()
    assert len(notebook_list) > 0
    storage["notebook_name_too_big"] = notebook_list[0]['name']
    storage["notebook_name"] = notebook_list[1]['name']


@pytest.mark.asyncio
async def test_nbs_content(client, storage):

    # fetch me
    def mock_func(_):
        return 'Bearer', storage['token']

    auth_bearer.get_cookies = mock_func

    headers = {'Accept': 'application/json',
               "Authorization": f"Bearer {storage['token']}"}

    github_username = storage['github_username']
    repo_name = storage['repo_name']
    branch_list = storage['branch_name']
    notebook_name = storage['notebook_name_too_big']
    response = await client.get(f"/repository/{github_username}/{repo_name}/{branch_list}/{notebook_name}", headers=headers)
    assert response.status_code == 413

    notebook_name = storage['notebook_name'].replace("/", "|")
    response = await client.get(f"/repository/{github_username}/{repo_name}/{branch_list}/{notebook_name}", headers=headers)
    assert response.status_code == 200
    notebook: schema.Notebook = response.json()
    assert notebook['contents'] != None


@pytest.mark.asyncio
async def test_nbs_check(client, storage):

    # fetch me
    def mock_func(_):
        return 'Bearer', storage['token']

    auth_bearer.get_cookies = mock_func

    headers = {'Accept': 'application/json',
               "Authorization": f"Bearer {storage['token']}"}

    github_username = storage['github_username']
    repo_name = "inference_nbs"
    branch_list = "main"
    notebook_name = "yolov5/pretrained_pil_inference.ipynb"
    notebook_name = notebook_name.replace("/", "|")
    response = await client.get(f"/repository/{github_username}/{repo_name}/{branch_list}/{notebook_name}/check", headers=headers)
    assert response.status_code == 200
