# python3.8 lambda base image
# aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws
FROM public.ecr.aws/lambda/python:latest as builder

RUN yum -y update 
RUN yum -y install gcc gcc-c++ make \
    && yum -y install tar \
    && yum -y install gzip \
    && yum -y install wget \
    && yum -y install unzip \
    && yum -y install git \
    && yum -y install mesa-libGL \
    && yum clean all

# general libraries
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" --upgrade pip
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" python-dotenv
RUN python3 -m pip install torch==1.9.0+cpu torchvision==0.10.0+cpu torchaudio==0.9.0 -f https://download.pytorch.org/whl/torch_stable.html
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" numpy==1.21.1
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" pandas==1.3
RUN python3 -m pip install --no-cache-dir opencv-python-headless
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" requests==2.26.0 
RUN python3 -m pip install --no-cache-dir jupyter==1.0.0 
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" boto3==1.18.6
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" PyYAML==5.4.1
RUN python3 -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" tqdm==4.61.2

FROM builder as builder_pip
