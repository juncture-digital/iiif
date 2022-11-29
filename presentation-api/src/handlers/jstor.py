#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

import json

import yaml
from urllib.parse import quote

from handlers.handler_base import HandlerBase

from licenses import CreativeCommonsLicense, RightsStatement

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

CONFIG = yaml.load(open(f'{BASEDIR}/config.yaml', 'r').read(), Loader=yaml.FullLoader)
JSTOR_API_KEY = CONFIG.get('JSTOR_API_KEY')

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    return url.startswith('https://www.jstor.org')

  @staticmethod
  def sourceid_from_url(url):
    return '/'.join(url.split('?')[0].split('/')[4:])

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'jstor:{sourceid.replace("?","%3F").replace("&","%26")}'
  
  def __init__(self, sourceid, **kwargs):
    self._raw_props = None
    super().__init__('jstor', sourceid, **kwargs)

  def init_manifest(self):
    props = self.raw_props

    self.label = props.get('item_title')
    self.summary = ' '.join(props.get('ps_desc',[]))

    iiif_url_fragment = props['iiifUrls'][0].split("/iiif/")[1] if 'iiifUrls' in props and len(props['iiifUrls']) > 0 else None
    image_service = f'https://www.jstor.org/iiif/{iiif_url_fragment}' if iiif_url_fragment else None
    self.image_url =  f'{image_service}/full/full/0/default.jpg' if image_service else None
    self.source_url = f'https://www.jstor.org/stable/{self.sourceid}'

    image_info = props['iiif_info']
    self.format = 'image/jpeg'
    self.width = image_info.get('width', 0)
    self.height = image_info.get('height', 0)

    self.add_metadata('creator', '; '.join(props.get('primary_agents',[])))
    self.add_metadata('tags', props.get('primary_agents',[]))

    self.thumbnail = f'{image_service}/full/150,/0/default.jpg' if image_service else None,

    if 'cc_reuse_license' in props and len(props['cc_reuse_license']) == 1:
      license_code = None
      if props['cc_reuse_license'][0] == 'Creative Commons: Free Reuse (CC0)': license_code = 'CC0'
      elif props['cc_reuse_license'][0] == 'Creative Commons: Public Domain Mark': license_code = 'PDM'
      elif props['cc_reuse_license'][0] == 'Creative Commons: Attribution': license_code = 'CC BY'
      elif props['cc_reuse_license'][0] == 'Creative Commons: Attribution-ShareAlike': license_code = 'CC BY-SA'
      elif props['cc_reuse_license'][0] == 'Creative Commons: Attribution-NonCommercial': license_code = 'CC BY-NC'
      elif props['cc_reuse_license'][0] == 'Creative Commons: Attribution-NoDerivs': license_code = 'CC BY-ND'
      elif props['cc_reuse_license'][0] == 'Creative Commons: Attribution-NonCommercial-ShareAlike': license_code = 'CC BY-NC-SA'
      elif props['cc_reuse_license'][0] == 'Creative Commons: Attribution-NonCommercial-NoDerivs': license_code = 'CC BY-NC-ND'
      else: license_code = props['cc_reuse_license'][0]
      
      LicenseType = None
      if license_code in CreativeCommonsLicense.licenses: LicenseType = CreativeCommonsLicense
      elif license_code in RightsStatement.statements: LicenseType = RightsStatement
      if LicenseType:
        self.rights = LicenseType(license=license_code).url
    
    self.provider = {
      'id': 'https://about.jstor.org/whats-in-jstor/open-community-collections/',
      'type': 'Agent',
      'label': {self.language: ['JSTOR Community Collections']},
      'homepage': [{
        'id': 'https://www.jstor.org',
        'label': {self.language: ['JSTOR']},
        'language': [self.language],
        'type': 'Text'
      }],
      'logo': [{
        'id': 'https://about.jstor.org/wp-content/themes/aboutjstor2017/static/JSTOR_Logo2017_90.png',
        'type': 'Image',
        'width': 90
      }]
    }

    if self.is_attribution_required and 'ps_source' in props:
      self.set_requiredStatement({'label': 'attribution', 'value': props['ps_source']})

  @property
  def raw_props(self):
    if self._raw_props is None:
      resp = requests.get(
        f'https://www.jstor.org/api/labs-search-service/metadata/10.2307/{self.sourceid}',
        headers = {
          'Content-Type': 'application/json',
          'User-Agent': 'Labs python client',
          'Authorization': f'Bearer {JSTOR_API_KEY}'
        }
      )
      props = resp.json() if resp.status_code == 200 else {}
      iiif_url_fragment = props['iiifUrls'][0].split("/iiif/")[1] if 'iiifUrls' in props and len(props['iiifUrls']) > 0 else None
      if iiif_url_fragment:
        info_json_url = f'https://www.jstor.org/iiif/{iiif_url_fragment}/info.json'
        resp = requests.get(f'https://api.visual-essays.net/image-info/?url={quote(info_json_url)}')
        props['iiif_info'] = resp.json() if resp.status_code == 200 else {}
      self._raw_props = props
    return self._raw_props
  
  def info_json(self):
    return self.props['iiif_info']

  def _service_endpoint(self):
    iiif_url_fragment = self.raw_props['iiifUrls'][0].split("/iiif/")[1] if 'iiifUrls' in self.raw_props and len(self.raw_props['iiifUrls']) > 0 else None
    return f'https://www.jstor.org/iiif/{iiif_url_fragment}' if iiif_url_fragment else None
