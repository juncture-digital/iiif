#!/bin/bash

cd "$(dirname "$0")"
mkdir -p build
rsync -va Dockerfile build
rsync -va ../src/app.py build

docker build -t iiif-convert build
docker run -it --env-file aws-creds iiif-convert

rm -rf build