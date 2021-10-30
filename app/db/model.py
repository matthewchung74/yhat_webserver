import json

from sqlalchemy import Column, String, Integer, DefaultClause, ForeignKey, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql.schema import ForeignKey
from sqlalchemy.sql.sqltypes import Boolean, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import TypeDecorator, VARCHAR
from sqlalchemy.ext.mutable import MutableDict

from sqlalchemy.sql import func

from app.db.database import Base
from app.db import schema

# https://docs.sqlalchemy.org/en/14/core/custom_types.html#marshal-json-strings
class JSONEncodedDict(TypeDecorator):
    impl = VARCHAR
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


json_type = MutableDict.as_mutable(JSONEncodedDict)


class User(Base):
    # user is reserved in postgres, thus user_account
    __tablename__ = "user_account"
    id = Column(
        UUID, primary_key=True, server_default=DefaultClause(text("gen_random_uuid()"))
    )
    avatar_url = Column(String, nullable=True)
    company = Column(String, nullable=True)
    html_url = Column(String, nullable=True)
    fullname = Column(String, nullable=True)
    email = Column(String, nullable=False, index=True)
    github_id = Column(String, nullable=True, unique=True)
    github_username = Column(String, nullable=True, unique=True)
    github_token = Column(String, nullable=True)
    type = Column(String, nullable=True)
    company = Column(String, nullable=True)
    early_access = Column(Boolean, nullable=True)
    created_at = Column("created_at", TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column("updated_at", TIMESTAMP(timezone=True), onupdate=func.now())

    def update_from_schema(self, user: schema.User):
        self.avatar_url = user.avatar_url
        self.company = user.company
        self.html_url = user.html_url
        self.fullname = user.fullname
        self.email = user.email
        self.github_id = user.github_id
        self.github_username = user.github_username
        self.github_token = user.github_token
        self.type = user.type


class Build(Base):
    __tablename__ = "build"
    id = Column(
        UUID, primary_key=True, server_default=DefaultClause(text("gen_random_uuid()"))
    )
    model_id = Column(String, nullable=False, index=True)
    github_username = Column(String, nullable=False, index=True)
    repository = Column(String, nullable=False, index=True)
    branch = Column(String, nullable=False, index=True)
    notebook = Column(String, nullable=False, index=True)
    commit = Column(String, nullable=True, index=True)
    duration = Column(Integer, nullable=True)
    user_id = Column(UUID, ForeignKey("user_account.id"), nullable=False, index=True)
    worker_server = Column(String, nullable=True)
    status = Column(String, nullable=False)
    input_json = Column(json_type, nullable=True)
    output_json = Column(json_type, nullable=True)
    lambda_function_arn = Column(String, nullable=True)
    docker_image_size = Column(Integer, nullable=True)
    docker_image_uri = Column(String, nullable=True)
    release_notes = Column(String, nullable=True)
    build_log = Column(String, nullable=True)
    last_run = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column("created_at", TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column("updated_at", TIMESTAMP(timezone=True), onupdate=func.now())


class Model(Base):
    __tablename__ = "model"
    id = Column(
        UUID, primary_key=True, server_default=DefaultClause(text("gen_random_uuid()"))
    )
    github_username = Column(String, nullable=False, index=True)
    repository = Column(String, nullable=False, index=True)
    notebook = Column(String, nullable=False, index=True)
    branch = Column(String, nullable=True, index=False)
    commit = Column(String, nullable=True, index=False)
    user_id = Column(UUID, ForeignKey("user_account.id"), nullable=False, index=True)
    user = relationship("User", foreign_keys=[user_id])
    active_build_id = Column(UUID, ForeignKey("build.id"), nullable=True)
    active_build = relationship("Build", foreign_keys=[active_build_id])
    title = Column(String, nullable=True, index=True)
    description = Column(String, nullable=True)
    credits = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    status = Column(String, nullable=True)
    created_at = Column("created_at", TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column("updated_at", TIMESTAMP(timezone=True), onupdate=func.now())


class Run(Base):
    __tablename__ = "run"
    id = Column(UUID, primary_key=True)
    user_id = Column(UUID, ForeignKey("user_account.id"), nullable=False, index=True)
    input_json = Column(json_type, nullable=True)
    output_json = Column(json_type, nullable=True)
    model_id = Column(UUID, ForeignKey("model.id"), nullable=False, index=True)
    build_id = Column(UUID, ForeignKey("build.id"), nullable=True, index=False)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column("created_at", TIMESTAMP(timezone=True), default=func.now())
