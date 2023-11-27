#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

OPENVERSE_CLIENT_ID = 'dSfaKEBUrRFYuN5UQyp6WXIL1YtzkH8HscMZcWo6'
OPENVERSE_CLIENT_SECRET = os.environ.get('OPENVERSE_CLIENT_SECRET')

from handlers.handler_base import HandlerBase
from licenses import CreativeCommonsLicense, RightsStatement

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

access_token = None

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    return url.startswith('https://search.creativecommons.org/') or \
      url.startswith('https://openverse.org/image') or \
      url.startswith('https://search.openverse.engineering/') or \
      url.startswith('https://wordpress.org/openverse/') or \
      url.startswith('https://search-production.openverse.engineering/image')

  @staticmethod
  def sourceid_from_url(url):
    return url.split('/')[-1].split('?')[0]

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'cc:{sourceid.replace("?","%3F").replace("&","%26")}'
  
  def __init__(self, sourceid, **kwargs):
    super().__init__('cc', sourceid, **kwargs)

  def _get_access_token(self):
    resp = requests.post(
      f'https://api.openverse.engineering/v1/auth_tokens/token/',
      data={
        'client_id': OPENVERSE_CLIENT_ID,
        'client_secret': OPENVERSE_CLIENT_SECRET,
        'grant_type': 'client_credentials'
      }
    )
    return resp.json()['access_token'] if resp.status_code == 200 else None

  def init_manifest(self):
    props = self.raw_props

    self.image_url = props.get('url')
    self.image_source = props.get('url')

    self.label = props.get('title')
    self.width = props.get('width', 0)
    self.height = props.get('height', 0)
    self.format = f'image/{props["url"].split(".")[-1].replace("jpg","jpeg")}'
    if 'license' in props:
      license_code = props['license'].upper()
      license_code = license_code if license_code in ('PDM', 'CC0') else f'CC {license_code}'
      LicenseType = None
      if license_code in CreativeCommonsLicense.licenses: LicenseType = CreativeCommonsLicense
      elif license_code in RightsStatement.statements: LicenseType = RightsStatement
      if LicenseType:
        self.rights = LicenseType(license=license_code).url
      if self.is_attribution_required() and 'attribution' in props:
        self.set_requiredStatement({'label': 'attribution', 'value': props['attribution']})
    if 'creator' in props:
      if 'creator_url' in props:
        self.add_metadata('creator', f'<a href="{props["creator_url"]}">{props["creator"]}</a>')
    else:
      self.add_metadata('creator', props['creator'])
    if 'source' in props:
      if 'foreign_landing_url' in props:
        self.add_metadata('source_url', f'<a href="{props["foreign_landing_url"]}">{props["source"]}</a>')
      else:
        self.add_metadata('source_url', props['source'])
    tags = [tag['name'] for tag in props['tags']] if props['tags'] else None
    if tags:
      self.add_metadata('tags', tags)

    self.provider = {
      'id': 'https://wordpress.org/openverse/',
      'type': 'Agent',
      'label': {self.language: ['openverse']},
      'homepage': [{
        'id': 'https://wordpress.org/openverse/',
        'label': {self.language: ['openverse']},
        'language': [self.language],
        'type': 'Text'
      }],
      'logo': [{
        'id': 'https://i0.wp.com/wordpressfoundation.org/content/uploads/2022/02/openverse.jpeg',
        'type': 'Image',
        'width': 150
      }]
    }

  @property
  def raw_props(self):
    global access_token
    if access_token is None:
      access_token = self._get_access_token()
    resp = requests.get(
      f'https://api.openverse.engineering/v1/images/{self.sourceid}',
      headers = {'Authorization': f'Bearer {access_token}'}
    )
    return resp.json() if resp.status_code == 200 else {}
