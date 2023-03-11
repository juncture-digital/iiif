#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os, json
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

from handlers.handler_base import HandlerBase
from licenses import CreativeCommonsLicense, RightsStatement

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    return url.startswith('https://www.metmuseum.org/art/collection/')

  @staticmethod
  def sourceid_from_url(url):
    return [elem for elem in url.split('/') if elem != ''][-1]

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'met:{sourceid.replace("?","%3F").replace("&","%26")}'
  
  def __init__(self, sourceid, **kwargs):
    super().__init__('met', sourceid, **kwargs)

  def init_manifest(self):
    props = self.raw_props
    # logger.info(json.dumps(props, indent=2))

    self.image_url = props.get('primaryImage')
    self.source_url = f'https://www.metmuseum.org/art/collection/search/{self.sourceid}'

    image_info = self._media_info(self.image_url)
    if 'objectWikidata_URL' in props:
      self.add_metadata('digital representation of', props['objectWikidata_URL'].split('/')[-1])
    if 'tags' in props:
      qids = [tag['Wikidata_URL'].split('/')[-1] for tag in props['tags'] if 'Wikidata_URL' in tag]
      if len(qids) > 0:
        self.add_metadata('depicts', qids)
    if 'artistWikidata_URL' in props:
      self.add_metadata('artist', props['artistWikidata_URL'].split('/')[-1])
    if 'objectDate' in props:
      self.navDate = props['objectDate']

    self.label = props.get('title')
    license_code = 'CC0' if props.get('isPublicDomain', False) else 'UND'
    LicenseType = None
    if license_code in CreativeCommonsLicense.licenses: LicenseType = CreativeCommonsLicense
    elif license_code in RightsStatement.statements: LicenseType = RightsStatement
    if LicenseType:
      self.rights = LicenseType(license=license_code).url
    if props.get('creditLine'):
      self.add_metadata('creditLine', props.get('creditLine'))
      if self.is_attribution_required():
        self.set_requiredStatement({'label': 'attribution', 'value': props['creditLine']})
    self.format = image_info['format']
    self.width = image_info['width']
    self.height = image_info['height']
    self.add_metadata('size', image_info['size'])

    self.provider = {
      'id': 'https://www.metmuseum.org/',
      'type': 'Agent',
      'label': {self.language: ['Metropolitan Museum of Art ']},
      'homepage': [{
        'id': 'https://www.metmuseum.org/',
        'label': {self.language: ['Metropolitan Museum of Art ']},
        'language': [self.language],
        'type': 'Text'
      }],
      'logo': [{
        'id': 'https://seeklogo.com/images/M/metropolitan-art-museum-logo-3B8686F789-seeklogo.com.png',
        'type': 'Image',
        'width': 150
      }]
    }

  @property
  def raw_props(self):
    resp = requests.get(
      f'https://collectionapi.metmuseum.org/public/collection/v1/objects/{self.sourceid}',
      headers = {
          'Content-Type': 'application/json',
          'User-Agent': 'Labs python client'
      }
    )
    return resp.json() if resp.status_code == 200 else {}
