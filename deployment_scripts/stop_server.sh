#!/bin/bash

if which pm2 >/dev/null; then
    echo exists, running stop_server
    pm2 delete all
else
    echo pm2 does not exist, skipping stop_server
fi
