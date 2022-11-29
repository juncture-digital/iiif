#!/bin/bash

cd "$(dirname "$0")"
mkdir -p build
rsync -va Dockerfile build
rsync -va --exclude=__pycache__ ../src/ build

docker build -t juncture-iiif-presentation build
docker run -it -p 8000:8000 --env-file aws-creds juncture-iiif-presentation

rm -rf build