from typing import Dict, Optional
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Json
from sqlalchemy.sql.sqltypes import Boolean
from app.helpers.autocomplete import autocomplete
from typing import Any, Dict, AnyStr, List, Union
from datetime import datetime
from app.helpers.boto_helper import create_presigned_url
from pathlib import Path


class UserType(str, Enum):
    Anonymous = "Anonymous"
    NotEmailVerified = "NotEmailVerified"
    EmailVerified = "EmailVerified"
    GithubVerified = "GithubVerified"


class GithubUserLoginSchema(BaseModel):
    code: str

    class Config:
        schema_extra = {"example": {"code": "abc"}}


@autocomplete
class GithubUser(BaseModel):
    avatar_url: Optional[str]
    company: Optional[str]
    html_url: Optional[str]
    email: Optional[str]
    fullname: Optional[str]
    github_id: Optional[str]
    github_username: Optional[str]
    type: UserType
    github_token: Optional[str]

    class Config:
        orm_mode = True
        use_enum_values = True
        arbitrary_types_allowed = True


@autocomplete
class User(GithubUser):
    id: str

    class Config:
        orm_mode = True


@autocomplete
class ProfileUser(BaseModel):
    avatar_url: Optional[str]
    company: Optional[str]
    html_url: Optional[str]
    fullname: Optional[str]
    github_id: Optional[str]
    github_username: Optional[str]
    type: UserType
    id: str

    class Config:
        orm_mode = True
        use_enum_values = True
        arbitrary_types_allowed = True


@autocomplete
class Token(BaseModel):
    token: str
    user_id: UUID


@autocomplete
class Repository(BaseModel):
    full_name: str
    name: str
    default_branch: str
    id: str
    private: bool

    class Config:
        orm_mode = False


@autocomplete
class Branch(BaseModel):
    name: str
    commit: str

    class Config:
        orm_mode = False


@autocomplete
class Notebook(BaseModel):
    name: str
    contents: Optional[str]
    size: Optional[int]

    class Config:
        orm_mode = False


class BuildStatus(str, Enum):
    NotStarted = "NotStarted"
    Queued = "Queued"
    Started = "Started"
    Error = "Error"
    Cancelled = "Cancelled"
    Finished = "Finished"


@autocomplete
class Build(BaseModel):
    id: Optional[str]
    model_id: Optional[str]
    github_username: str
    repository: str
    branch: str
    notebook: str
    commit: Optional[str]
    duration: Optional[int]
    user_id: Optional[str]
    status = BuildStatus.NotStarted
    input_json: Optional[Dict]
    output_json: Optional[Dict]
    lambda_function_arn: Optional[str]
    docker_image_uri: Optional[str]
    docker_image_size: Optional[int]
    release_notes: Optional[str]
    build_log: Optional[str]
    last_run: Optional[datetime]

    class Config:
        orm_mode = True

    def get_github_url(self):
        branch = self.commit if self.commit != None else self.branch
        return f"http://github.com/{self.github_username}/{self.repository}/blob/{branch}/{self.notebook}"


class ModelStatus(str, Enum):
    Draft = "Draft"
    Public = "Public"
    Deleted = "Deleted"


@autocomplete
class Model(BaseModel):
    id: Optional[str]
    github_username: str
    repository: str
    notebook: str
    title: Optional[str]
    description: Optional[str]
    branch: Optional[str]
    commit: Optional[str]
    user_id: str
    user: Optional[ProfileUser]
    active_build_id: Optional[str]
    active_build: Optional[Build]
    tags: Optional[str]
    status: Optional[ModelStatus]
    updated_at: Optional[datetime]
    created_at: Optional[datetime]

    class Config:
        orm_mode = True
        use_enum_values = True
        arbitrary_types_allowed = True


@autocomplete
class Run(BaseModel):
    id: Optional[str]
    input_json: Optional[Dict]
    output_json: Optional[Dict]
    thumb_json: Optional[Dict]
    build_id: str
    model_id: str
    user_id: str
    duration_ms: Optional[int]
    created_at: Optional[datetime]

    class Config:
        orm_mode = True

    def add_signed_urls(self):
        self.thumb_json = {}

        for key, value in self.input_json.items():
            if value.startswith("s3://"):
                self.input_json[key] = create_presigned_url(
                    bucket_name=Path(value).parts[1],
                    object_name="/".join(Path(value).parts[2:]),
                )
                self.thumb_json[self.input_json[key]] = create_presigned_url(
                    bucket_name=Path(value).parts[1],
                    object_name="/".join(Path(value).parts[2:]).replace(
                        ".jpg", "-thumb.jpg"
                    ),
                )

        for key, value in self.output_json.items():
            if value.startswith("s3://"):
                self.output_json[key] = create_presigned_url(
                    bucket_name=Path(value).parts[1],
                    object_name="/".join(Path(value).parts[2:]),
                )
                self.thumb_json[self.output_json[key]] = create_presigned_url(
                    bucket_name=Path(value).parts[1],
                    object_name="/".join(Path(value).parts[2:]).replace(
                        ".jpg", "-thumb.jpg"
                    ),
                )


JSONObject = Dict[AnyStr, Any]
JSONArray = List[Any]
JSONStructure = Union[JSONArray, JSONObject]
