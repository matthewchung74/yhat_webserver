apt install -y nodejs
apt install -y npm
npm install pm2@latest -g

sudo systemctl stop apache2

if [ "$APPLICATION_NAME" == "YHatBuilder" ]
then
    sudo apt install -y awscli
    echo '{"max-concurrent-uploads": 1 }' > /etc/docker/daemon.json

    sudo systemctl daemon-reload
    sudo systemctl restart docker

    sudo systemctl start apache2

    $(aws ecr get-login --region us-east-1 --no-include-email)
    docker pull public.ecr.aws/c6h1o1s4/inference_lambda_public:base_pytorch
fi
