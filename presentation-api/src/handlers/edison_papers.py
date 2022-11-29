#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

from handlers.handler_base import HandlerBase

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    path_elems = url.split('/')
    return len(path_elems) > 3 and path_elems[2] == 'edisondigital.rutgers.edu' and path_elems[3] in ('document', 'iiif')

  @staticmethod
  def sourceid_from_url(url):
    return url.split('/')[4]

  @staticmethod
  def manifest_url(url, baseurl=None):
    sourceid = Handler.sourceid_from_url(url)
    return f'https://edisondigital.rutgers.edu/iiif/{sourceid}'

  def __init__(self, url, **kwargs):
    self._url = url
    super().__init__('edison', Handler.sourceid_from_url(url), **kwargs)
