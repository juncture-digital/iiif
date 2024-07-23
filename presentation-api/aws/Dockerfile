FROM ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y git python3-pip python3-dev libmagic-dev ffmpeg \
  && cd /usr/local/bin \
  && ln -s /usr/bin/python3 python \
  && rm -rf /var/lib/apt/lists/*

ENV APP_HOME /usr/src/app

WORKDIR $APP_HOME

RUN python3 -m pip install --break-system-packages awslambdaric
COPY requirements.txt ./
RUN pip install --break-system-packages -r requirements.txt

COPY .  ./

ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]
CMD ["main.handler"]