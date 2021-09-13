#!/bin/bash
cd /home/ubuntu/inference_server/ 
pm2 start "venv/bin/python -m app.service.builder_server.builder_server" --name builder
