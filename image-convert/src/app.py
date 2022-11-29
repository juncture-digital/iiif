#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

import os
import argparse
import json
from hashlib import sha256
import pyvips
logging.getLogger('pyvips').setLevel(logging.WARNING)

import boto3

import requests
logging.getLogger('requests').setLevel(logging.INFO)

QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/804803416183/iiif-convert'

TEST_IMAGE = 'https://upload.wikimedia.org/wikipedia/commons/0/0f/1665_Girl_with_a_Pearl_Earring.jpg'

BUCKET_NAME = 'iiif-img'
if 'AWS_LAMBDA_FUNCTION_NAME' in os.environ:
  s3 = boto3.client('s3')
else:
  s3 = boto3.Session(
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
  ).client('s3')

def exists(key):
  return s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=key)['KeyCount'] > 0

def download_image(url):
  logger.info(f'download_image: url={url}')
  resp = requests.get(url, headers={'User-agent': 'IIIF service'})
  if resp.status_code == 200:
    fname = sha256(url.encode('utf-8')).hexdigest()
    with open(f'/tmp/{fname}', 'wb') as fp:
      fp.write(resp.content)
    return fname

def convert(src, dest, quality=50, **kwargs):
  logger.info(f'convert: src={src} dest={dest}')
  img = pyvips.Image.new_from_file(f'/tmp/{src}')
  img.tiffsave(
    f'/tmp/{dest}',
    tile=True,
    compression='jpeg',
    pyramid=True, 
    Q=quality,
    tile_width=512,
    tile_height=512
  )

def save_to_s3(fname):
    logger.info(f'save_to_s3: bucket={BUCKET_NAME} fname={fname}')
    s3.upload_file(f'/tmp/{fname}', BUCKET_NAME, fname)

def main(**kwargs):
  refresh = kwargs.get('refresh', False)
  src = download_image(kwargs['url'])
  dest = f'{src}.tif'
  if refresh or not exists(dest):
    convert(src, dest, **kwargs)
    save_to_s3(dest)
    # if os.path.exists(f'/tmp{src}'): os.remove(f'/tmp{src}')
    if os.path.exists(f'/tmp{dest}'): os.remove(f'/tmp{dest}')

def handler(event, context):
  logger.setLevel(logging.INFO)
  logger.info(json.dumps(event, indent=2))

  for message in event['Records']:
    receipt_handle = message['receiptHandle']
    image_url = message['messageAttributes']['url']['stringValue']
    quality = int(message['messageAttributes']['quality']['stringValue']) if 'quality' in message['messageAttributes'] else 70
    refresh = message['messageAttributes']['refresh']['stringValue'].lower() == 'true' if 'refresh' in message['messageAttributes'] else False

    sqs_client = boto3.client('sqs', region_name='us-east-1')
    sqs_client.delete_message(
      QueueUrl=QUEUE_URL,
      ReceiptHandle=receipt_handle
    )
    main(url=image_url, quality=quality, refresh=refresh)

if __name__ == '__main__':
  logger.setLevel(logging.INFO)
  parser = argparse.ArgumentParser(description='Image Info')
  parser.add_argument('url', help='Image URL', default=TEST_IMAGE)
  parser.add_argument('--quality', help='Image quality', type=int, default=50)
  parser.add_argument('--refresh', help='Refresh if exists', type=bool, default=False)
  main(**vars(parser.parse_args()))
