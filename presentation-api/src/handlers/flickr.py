#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

from handlers.handler_base import HandlerBase
from licenses import CreativeCommonsLicense, RightsStatement

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

FLICKR_API_KEY = os.environ.get('FLICKR_API_KEY')

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    return url.startswith('https://www.flickr.com/photos') or url.startswith('https://live.staticflickr.com')
  
  @staticmethod
  def sourceid_from_url(url):
    if url.startswith('https://www.flickr.com/photos'):
      return [elem for elem in url.split('/')[4:] if elem.isdigit()][0]
    else:
      return url.split('/')[4].split('_')[0]

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'flickr:{sourceid.replace("?","%3F").replace("&","%26")}'
  
  # from https://www.flickr.com/services/rest/?method=flickr.photos.licenses.getInfo&api_key={API_KEY}&format=json&nojsoncallback=1
  flickr_licenses = {
    '0': 'InC',
    '1': 'CC BY-NC-SA 2.0',
    '2': 'CC BY-NC 2.0',
    '3': 'CC BY-NC-ND 2.0',
    '4': 'CC BY 2.0',
    '5': 'CC BY-SA 2.0',
    '6': 'CC BY-ND 2.0',
    '7': '<a href="https://www.flickr.com/commons/usage/">No known copyright restrictions</a>',
    '8': '<a href="http://www.usa.gov/copyright.shtml">United States Government Work</a>',
    '9': 'CC0 1.0',
    '10': 'PDM'
  }

  def __init__(self, sourceid, **kwargs):
    super().__init__('flickr', sourceid, **kwargs)

  def init_manifest(self):
    props = self.raw_props
    # logger.info(json.dumps(props, indent=2))
    self.image_source = props.get('size',{}).get('source')
    self.label = props.get('title',{}).get('_content')
    self.summary = props.get('description',{}).get('_content')
    self.source_url = f'https://www.flickr.com/photos/{props["owner"]["nsid"]}/{self.sourceid}'
    self.image_url = props.get('size',{}).get('source')

    license_data = self.flickr_licenses.get(props.get('license')).split()
    if len(license_data) == 1:
      rightsCode = license_data[0]
      version = '1.0'
    else:
      rightsCode = ' '.join(license_data[:2])
      version = license_data[-1]
    LicenseType = None
    if rightsCode in CreativeCommonsLicense.licenses: LicenseType = CreativeCommonsLicense
    elif rightsCode in RightsStatement.statements: LicenseType = RightsStatement
    if LicenseType:
      self.rights = LicenseType(license=rightsCode, version=version).url
    
    owner = f'<a href="https://www.flickr.com/photos/{props["owner"]["nsid"]}/">{props["owner"]["realname"] if props["owner"]["realname"] != "" else props["owner"]["username"] }</a>'
    self.add_metadata('creator', owner)

    if self.is_attribution_required() and not self.has_attribution_statement():
      self.set_requiredStatement({'label': 'attribution', 'value': f'Provided by {owner}'})

    self.provider = {
      'id': 'https://www.flickr.com/about',
      'type': 'Agent',
      'label': {self.language: ['Flickr']},
      'homepage': [{
        'id': 'https://www.flickr.com/',
        'label': {self.language: ['Flickr']},
        'language': [self.language],
        'type': 'Text'
      }],
      'logo': [{
        'id': 'https://upload.wikimedia.org/wikipedia/commons/4/44/Flickr.svg',
        'type': 'Image',
        'width': 150
      }]
    }

    self.format = 'image/jpeg'
    self.width = props.get('size',{}).get('width',0)
    self.height = props.get('size',{}).get('height',0)

    tags = [tag['_content'] for tag in props['tags']['tag']]
    if tags:
      self.add_metadata('tags', tags)

  @property
  def raw_props(self):
    props = {}
    url = f'https://www.flickr.com/services/rest/?method=flickr.photos.getInfo&api_key={FLICKR_API_KEY}&photo_id={self.sourceid}&format=json&nojsoncallback=1'
    resp = requests.get(url)
    if resp.status_code == 200:
      props = resp.json()['photo']
      resp = requests.get(f'https://www.flickr.com/services/rest/?method=flickr.photos.getSizes&api_key={FLICKR_API_KEY}&photo_id={self.sourceid}&format=json&nojsoncallback=1')
      props['size'] = sorted(resp.json()['sizes']['size'], key = lambda i: i['width'])[-1]
    return props    
