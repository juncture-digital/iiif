#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import traceback
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import os
import sys
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

import magic
import filetype

import ffmpeg

import boto3
from s3 import Bucket
thumbnail_cache = Bucket('iiif-thumbnail')

class MediaInfo(object):

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
        data['coordinates_of_the_point_of_view'] = f'{lat},{lon}'
    except:
      logger.debug(traceback.format_exc())
    return data

  def from_info_json(self, url):
    resp = requests.get(url,
      cookies={'UUID': str(uuid.uuid4())},
      headers={
        'User-Agent': 'Labs client',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
      }
    )
    logger.debug(f'{url} {resp.status_code}')
    return resp.json() if resp.status_code == 200 else {}

  def download(self, url):
    path = f'/tmp/{sha256(url.encode("utf-8")).hexdigest()}'
    resp = requests.get(url, headers={'User-agent': 'IIIF service'})
    if resp.status_code == 200:
      with open (path, 'wb') as fp:
        fp.write(resp.content)
    return path if resp.status_code == 200 else None

  def image_info(self, path):
    info = {}
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
    return info

  def av_info(self, path):
    return ffmpeg.probe(path)['streams'][0]
    
  def __call__(self, url, **kwargs):
    logger.debug(f'media_info: url={url}')
    media_info = {}
    if url.endswith('/info.json'):
      media_info = self.from_info_json(url)
    elif url.startswith('https://www.jstor.org/iiif'):
      url = f'{"/".join(url.split("/")[:-4])}/info.json'
      media_info = self.from_info_json(url)
      logger.debug(media_info)

    else:
      path = self.download(url)
      if path:
        mime = magic.from_file(path, mime=True)
        # kind = filetype.guess(path)
        # mime = kind.mime if kind else None
        _type = mime.split('/')[0]
        if _type in ('audio', 'video'):
          av_info = self.av_info(path)
          if av_info:
            if 'display_aspect_ratio' in av_info:
              wh = [int(v) for v in av_info['display_aspect_ratio'].split(':')]
              aspect = wh[0]/wh[1]
              av_info['width'] = round(av_info['height'] * aspect)
            media_info = {
              'format': mime,
              'size': os.stat(path).st_size
            }
            for fld in ('duration', 'height', 'width'):
              if fld in av_info:
                media_info[fld] = av_info[fld]
            if 'duration' in media_info:
              media_info['duration'] = round(float(media_info['duration']), 1)
        else:
          media_info = self.image_info(path)
        os.remove(path)
    logger.debug(json.dumps(media_info, indent=2))
    return media_info
  
  def _create_presigned_url(self, bucket_name, object_name, expiration=600):
    boto3.setup_default_session()
    # Generate a presigned URL for the S3 object
    s3_client = boto3.client(
      's3',
      region_name='us-east-1',
      config=boto3.session.Config(signature_version='s3v4',)
    )
    try:
      response = s3_client.generate_presigned_url(
        'get_object',
        Params={
          'Bucket': bucket_name,
          'Key': object_name,
          'ResponseContentType': 'image/jpeg'
        },
        ExpiresIn=expiration
      )
    except Exception as e:
        print(e)
        logging.error(e)
        return 'Error'
    return response

  def poster(self, url, time, refresh=False):
    _id = sha256(f'{url}_{str(time)}'.encode('utf-8')).hexdigest()
    
    if not refresh and _id in thumbnail_cache:
      return self._create_presigned_url('iiif-thumbnail', _id)

    input_path = self.download(url)
    image_path = f'/tmp/{_id}.jpg'

    probe = ffmpeg.probe(input_path)
    width = probe['streams'][0]['width']
    try:
      (
        ffmpeg
        .input(input_path, ss=time)
        .filter('scale', width, -1)
        .output(image_path, vframes=1)
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
      )
    
      img = None
      with open(image_path, 'rb') as fp:
        img = fp.read()
      os.remove(input_path)
      os.remove(image_path)
      
      if img:
        thumbnail_cache[_id] = img
        return self._create_presigned_url('iiif-thumbnail', _id)

    except ffmpeg.Error as e:
      print(e.stderr.decode(), file=sys.stderr)


if __name__ == '__main__':
  logger.setLevel(logging.INFO)
  parser = argparse.ArgumentParser(description='Media Info')
  parser.add_argument('url', help='Media URL')

  client = MediaInfo()
  results = client.__call__(**vars(parser.parse_args()))
  print(json.dumps(results))