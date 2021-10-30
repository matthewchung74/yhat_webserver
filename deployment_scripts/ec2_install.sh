#!/bin/bash
sudo apt-get update -y 
sudo apt-get install ruby -y
sudo apt-get install wget -y

cd /home/ubuntu

wget https://aws-codedeploy-us-west-2.s3.us-west-2.amazonaws.com/latest/install
chmod +x ./install
sudo ./install auto

sudo apt install -y apache2
sudo ufw allow 'Apache'

sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
sudo apt-get install -y -q build-essential python3-venv git

sudo apt install -y nodejs npm 
sudo npm install pm2 -g
