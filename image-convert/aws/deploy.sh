#!/bin/bash

FUNCTION_NAME=${1:-iiif-convert}

cd "$(dirname "$0")"
mkdir -p build
rsync -va Dockerfile build
rsync -va ../src/app.py build

aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${AWS_ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com
docker buildx build --platform linux/amd64 --push -t ${AWS_ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/${FUNCTION_NAME} build 2>&1 | tee  ./build.log
aws lambda update-function-code --function-name ${FUNCTION_NAME} --image-uri ${AWS_ACCOUNT}.dkr.ecr.us-east-1.amazonaws.com/${FUNCTION_NAME}:latest

rm -rf build