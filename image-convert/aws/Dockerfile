FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y python3-pip python3-dev libvips \
  && cd /usr/local/bin \
  && ln -s /usr/bin/python3 python \
  && pip3 --no-cache-dir install --upgrade pip \
  && rm -rf /var/lib/apt/lists/*


ENV APP_HOME /usr/src/app
WORKDIR $APP_HOME

RUN pip install awslambdaric boto3 pyvips requests

COPY ./app.py ./

ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]
CMD ["app.handler"]