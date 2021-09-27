apt install -y nodejs
apt install -y npm
npm install pm2@latest -g

if [ "$APPLICATION_NAME" == "builder" ]
then
    apt install -y awscli
    echo '{"max-concurrent-uploads": 1 }' > /etc/docker/daemon.json

    systemctl daemon-reload
    systemctl restart docker

    $(aws ecr get-login --region us-east-1 --no-include-email)
    docker pull public.ecr.aws/c6h1o1s4/inference_lambda_public:base_pytorch
fi