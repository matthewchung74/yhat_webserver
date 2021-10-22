FROM public.ecr.aws/c6h1o1s4/inference_lambda_public:base_pytorch AS mybase

# https://pythonspeed.com/articles/activate-virtualenv-dockerfile/
# ENV VIRTUAL_ENV=./venv
# RUN python3 -m venv $VIRTUAL_ENV
# ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# RUN pip install --no-cache-dir  --upgrade --force-reinstall git+https://github.com/yhatpub/yhat_params.git@main

RUN python -m pip install --no-cache-dir --compile --global-option=build_ext --global-option="-j 4" --upgrade pip

COPY ./app/inference.py \
     ./app/inference.ipynb \
     ./app/app.py \
     /var/task/

RUN ipython inference.ipynb
RUN python inference.py

# RUN chmod 644 $(find . -type f)
# RUN chmod 755 $(find . -type d)

CMD [ "app.handler" ]

FROM mybase as mydebug

RUN mkdir /var/task/.vscode
RUN true
COPY ./app/.vscode/ /var/task/.vscode/
RUN true
COPY ./app/.env /var/task/.env
RUN python3 -m pip install --no-cache-dir debugpy
