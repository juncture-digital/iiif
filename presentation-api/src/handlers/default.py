#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

import yaml
from urllib.parse import quote, unquote

CONFIG = yaml.load(open(f'{BASEDIR}/config.yaml', 'r').read(), Loader=yaml.FullLoader)

from handlers.handler_base import HandlerBase

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

def is_image(url):
  return requests.head(url).headers.get('Content-Type','').startswith('image')

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    return is_image(url)

  @staticmethod
  def sourceid_from_url(url):
    return quote(url)
    
  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'{baseurl}/default:{sourceid.replace("?","%3F").replace("&","%26")}/manifest.json'

  def __init__(self, sourceid, **kwargs):
    super().__init__('default', sourceid, **kwargs)

  def init_manifest(self):
    self.image_url = unquote(self.sourceid)
    self.label = self.image_url
    self.rights = 'http://rightsstatements.org/vocab/CNE/1.0/'
