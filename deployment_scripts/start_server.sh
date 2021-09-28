#!/bin/bash

if [ "$APPLICATION_NAME" == "YHatBuilder" ]
then
    pm2 start "venv/bin/python -m app.service.builder_server.builder_server" --name builder
fi

if [ "$APPLICATION_NAME" == "YHatFastApi" ]
then
    pm2 start "venv/bin/python -m uvicorn app.api:app  --host 0.0.0.0 --port 8000" --name fastapi
fi
