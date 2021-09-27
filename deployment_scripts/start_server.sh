if [ "$APPLICATION_NAME" == "builder" ]
then
    pm2 start "venv/bin/python -m app.service.builder_server.builder_server" --name builder
fi

if [ "$APPLICATION_NAME" == "fastapi" ]
then
    pm2 start "venv/bin/python -m uvicorn app.api:app  --host 0.0.0.0 --port 8000" --name fastapi
fi
