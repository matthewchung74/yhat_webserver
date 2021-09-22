pm2 start "venv/bin/python -m uvicorn app.api:app  --host 0.0.0.0 --port 8000" --name fastapi
