#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

from handlers.handler_base import HandlerBase

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    path_elems = url.split('/')
    return len(path_elems) > 3 and path_elems[2] == 'archive.org/' and path_elems[3] in ('details,')

  @staticmethod
  def sourceid_from_url(url):
    return url.split('/')[4]

  @staticmethod
  def manifest_url(url, baseurl=None):
    sourceid = Handler.sourceid_from_url(url)  
    return f'https://iiif.archivelab.org/iiif/{sourceid}/manifest.json'
