#!/bin/bash

apt install -y nodejs
apt install -y npm
npm install pm2 -g
pm2 install pm2-logrotate

sudo systemctl stop apache2

echo "before_install $APPLICATION_NAME"

if [ "$APPLICATION_NAME" == "YHatBuilder" ]
then
    sudo apt install -y awscli
    echo '{"max-concurrent-uploads": 1 }' > /etc/docker/daemon.json

    sudo systemctl daemon-reload
    sudo systemctl restart docker

    echo "Listen 8000" >> /etc/apache2/ports.conf
    
    sudo systemctl start apache2

    $(aws ecr get-login --region us-east-1 --no-include-email)
    docker pull public.ecr.aws/c6h1o1s4/inference_lambda_public:base_pytorch
fi
