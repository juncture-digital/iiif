FROM python:3.9

ENV APP_HOME /app
WORKDIR $APP_HOME

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY .  ./

ENV PORT 8080

CMD exec gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --threads 8 main:app