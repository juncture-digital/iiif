#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

from handlers.handler_base import HandlerBase

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

def is_image(url):
  return requests.head(url).headers.get('Content-Type','').startswith('image')

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    path_elems = url.split('?')[0].split('/')
    return len(path_elems) > 3 and path_elems[2] == 'harvardartmuseums.org' and path_elems[3] in ('collections')

  @staticmethod
  def sourceid_from_url(url):
    return  url.split('?')[0].split('/')[5]

  @staticmethod
  def manifest_url(url, baseurl=None):
    sourceid = Handler.sourceid_from_url(url)
    return f'https://iiif.harvardartmuseums.org/manifests/object/{sourceid}'

  def __init__(self, url, **kwargs):
    self._url = url
    super().__init__('harvard', Handler.sourceid_from_url(url), **kwargs)
