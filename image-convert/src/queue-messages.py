#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)
logger = logging.getLogger()

import boto3
import json
import argparse
from hashlib import sha256

sqs_client = boto3.client('sqs')

QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/804803416183/iiif-convert'

def queue_message(**kwargs):
    attrs = {}
    attrs['url'] = {'DataType': 'String', 'StringValue': kwargs['url']}
    if kwargs.get('refresh', False):
      attrs['refresh'] = {'DataType': 'String', 'StringValue': 'true'}
    if 'quality' in kwargs:
      attrs['quality'] = {'DataType': 'String', 'StringValue': str(kwargs['quality'])}

    sqs_client.send_message(
        QueueUrl=QUEUE_URL,
        DelaySeconds=0,
        MessageAttributes=attrs,
        MessageBody=json.dumps(kwargs)
    )

    image_id = sha256(kwargs['url'].encode('utf-8')).hexdigest()
    # info_json = f'https://4x4rr42s5yd4hr7mdrjqp3euqm0hnpoe.lambda-url.us-east-1.on.aws/iiif/2/{image_id}/info.json'
    info_json = f'https://iiif-image.juncture-digital.org/iiif/2/{image_id}/info.json'
    return info_json

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Image Info')
  parser.add_argument('url', help='Image URL')
  parser.add_argument('--quality', help='Image quality', type=int, default=50)
  parser.add_argument('--refresh', help='Refresh if exists', type=bool, default=False)
  print(queue_message(**vars(parser.parse_args())))
