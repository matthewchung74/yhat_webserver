# https://www.youtube.com/watch?v=qQNGw_m8t0Y

# FROM ubuntu:latest
FROM public.ecr.aws/lts/ubuntu:20.04 AS builder

WORKDIR /app

RUN apt update && apt upgrade -y
RUN apt install -y apt-transport-https ca-certificates curl software-properties-common
RUN apt install -y -q build-essential python3-venv git

RUN apt install -y nodejs npm 
RUN npm install pm2 -g

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN python3 -m pip install poetry

RUN python3 -m pip install -U pip setuptools wheel requests
RUN python3 -m pip install gunicorn uvloop httptools
RUN python3 -m pip install uvicorn[standard]

ENV YOUR_ENV=${YOUR_ENV} \
    PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

COPY pyproject.toml pyproject.toml
COPY poetry.lock poetry.lock
RUN python3 -m pip install --upgrade pip
RUN poetry export -f requirements.txt --output requirements.txt  --without-hashes --dev
RUN python3 -m pip install -r requirements.txt

COPY .vscode .vscode

COPY app /app/app

FROM builder as tester
COPY ./deployment_scripts/run_tests.sh ./deployment_scripts/run_tests.sh

FROM builder as fastapi
CMD ["pm2", "start", "python -m uvicorn app.api:app  --host 0.0.0.0 --port 8000", "--no-daemon"]
