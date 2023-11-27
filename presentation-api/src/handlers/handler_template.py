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
    return 

  @staticmethod
  def sourceid_from_url(url):
    return

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'{baseurl}/<SOURCE>:{sourceid.replace("?","%3F").replace("&","%26")}/manifest.json'

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'{baseurl}/source_code:{sourceid.replace("?","%3F").replace("&","%26")}/manifest.json'
  
  def __init__(self, sourceid, **kwargs):
    super().__init__('source_code', sourceid, **kwargs)

  def init_manifest(self):
    props = self.raw_props

  @property
  def raw_props(self):
    return {}
