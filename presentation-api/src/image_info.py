#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import traceback
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import os
import argparse
import json
import uuid
from time import time as now
from hashlib import sha256

import requests
logging.getLogger('requests').setLevel(logging.INFO)

from PIL import Image
Image.MAX_IMAGE_PIXELS = 1000000000

import datetime

import exif

class ImageInfo(object):

  def __init__(self, **kwargs):
    pass

  def _decimal_coords(self, coords, ref):
    decimal_degrees = coords[0] + coords[1] / 60 + coords[2] / 3600
    if ref == 'S' or ref == 'W':
        decimal_degrees = -decimal_degrees
    return decimal_degrees

  def exif_data(self, img):
    data = {}
    try:
      exifImg = exif.Image(img)
      if exifImg.has_exif:
        data['created'] = datetime.datetime.strptime(exifImg.datetime_original, '%Y:%m:%d %H:%M:%S').strftime('%Y-%m-%dT%H:%M:%SZ')
        exifImg.gps_longitude
        lat = round(self._decimal_coords(exifImg.gps_latitude, exifImg.gps_latitude_ref),6)
        lon = round(self._decimal_coords(exifImg.gps_longitude,exifImg.gps_longitude_ref),6)
        data['location'] = f'{lat},{lon}'
    except:
      logger.debug(traceback.format_exc())
    return data

  def __call__(self, url, **kwargs):
    if url.endswith('/info.json'):
        resp = requests.get(url,
            cookies={'UUID': str(uuid.uuid4())},
            headers={
                'User-Agent': 'Labs client',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            }
        )
        return resp.status_code, resp.json() if resp.status_code == 200 else {}
    else:
        info = {}
        start = now()        
        path = f'/tmp/{sha256(url.encode("utf-8")).hexdigest()}'
        resp = requests.get(url, headers={'User-agent': 'IIIF service'})
        logger.info(f'{url} {resp.status_code}')
        if resp.status_code == 200:
            with open (path, 'wb') as fp:
                fp.write(resp.content)
            try:
              img = Image.open(path)
              info.update({
                  'format': Image.MIME[img.format],
                  'width': img.width,
                  'height': img.height,
                  'size': os.stat(path).st_size
              })
              info.update(self.exif_data(path))
            except:
              logger.error(traceback.format_exc())
            os.remove(path)
        logger.debug(f'__call__: url={url} kwargs={kwargs} elapsed={round(now()-start, 2)}')
        return resp.status_code, info

if __name__ == '__main__':
  logger.setLevel(logging.INFO)
  parser = argparse.ArgumentParser(description='Image Info')
  parser.add_argument('url', help='Image URL')

  client = ImageInfo()
  results = client.__call__(**vars(parser.parse_args()))
  print(json.dumps(results))