#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

import json
import re
import hashlib
from urllib.parse import quote, unquote

from handlers.handler_base import HandlerBase
from licenses import CreativeCommonsLicense, RightsStatement

# import requests
# logging.getLogger('requests').setLevel(logging.WARNING)

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    return url.startswith('https://commons.wikimedia.org') or\
           url.startswith('https://commons.m.wikimedia.org') or\
           url.startswith('https://upload.wikimedia.org/wikipedia/commons') or\
           ('wikipedia.org/wiki/' in url and '/File:' in url)

  @staticmethod
  def sourceid_from_url(url):
    if url.startswith('https://commons.wikimedia.org') or url.startswith('https://commons.m.wikimedia.org'):
      return url.split('File:')[-1]
    elif url.startswith('https://upload.wikimedia.org/wikipedia/commons'):
      path_elems = url.split('/')
      return path_elems[8] if path_elems[5] == 'thumb' else path_elems[-1]
    elif 'wikipedia.org/wiki/' in url and '/File:' in url:
      return url.split('File:')[-1]

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'wc:{sourceid.replace("?","%3F").replace("&","%26")}'
  
  def __init__(self, sourceid, **kwargs):
    self._raw_props = None
    super().__init__('wc', sourceid, **kwargs)

  def init_manifest(self):
    props = self.raw_props

    imageinfo = props['wc_metadata']['imageinfo'][0]
    extmetadata = imageinfo['extmetadata']
    
    self.image_url = self._image_url_from_sourceid()
    self.source_url = f'https://commons.wikimedia.org/wiki/File:{self.sourceid}'

    self.format = imageinfo['mime']
    
    if self.type in ('Image', 'Video') :
      self.width = imageinfo['width']
      self.height = imageinfo['height']

    if self.type == 'Image':
      # thumbnail width scaled to long side
      thumbnail_width = 240 if self.height > self.width else int(240 * self.width/self.height)
      self.thumbnail = [{'id': self._image_url_from_sourceid(thumbnail_width), 'type': 'Image'}]
    
    if 'duration' in imageinfo:
      self.duration = round(imageinfo['duration'], 1)

    self.label = self._extract_text(extmetadata['ObjectName']['value']) if 'ObjectName' in extmetadata else None
    self.summary = self._extract_text(extmetadata['ImageDescription']['value']) if 'ImageDescription' in extmetadata else None

    self.provider = {
      'id': 'https://commons.wikimedia.org/wiki/Main_Page',
      'type': 'Agent',
      'label': {self.language: ['Wikimedia Commons']},
      'homepage': [{
        'id': 'https://commons.wikimedia.org/wiki/Main_Page',
        'label': {self.language: ['Wikimedia Commons']},
        'language': [self.language],
        'type': 'Text'
      }],
      'logo': [{
        'id': 'https://upload.wikimedia.org/wikipedia/en/4/4a/Commons-logo.svg',
        'type': 'Image',
        'width': 150
      }]
    }

    license_str = None
    for fld in ('LicenseShortName', 'License'):
      if fld in extmetadata:
        license_str = extmetadata[fld]['value'].upper()
        break
    if license_str:
      _match = re.search(r'-?(\d\.\d)\s*$', license_str)
      version = _match[1] if _match else None
      license = re.sub(r'-?\d\.\d\s*$', '', license_str).strip()
      # logger.info(f'{license_str} license={license} version={version}')
      LicenseType = None
      if license in CreativeCommonsLicense.licenses: LicenseType = CreativeCommonsLicense
      elif license in RightsStatement.statements: LicenseType = RightsStatement
      if LicenseType:
        self.rights = LicenseType(license=license, version=version).url
    
    if self.is_attribution_required() and not self.has_attribution_statement():
      for fld in ['Attribution', 'Artist']:
        if fld in extmetadata:
          owner = extmetadata[fld]['value'].replace('<big>','').replace('</big>','')
          self.set_requiredStatement({'label': 'attribution', 'value': owner})
          break
  
    if 'wc_entity' in props:
      _depicts = [item['id'] for item in self._depicts(props['wc_entity'])]
      if len(_depicts) > 0:
        self.add_metadata(self._language_map('depicts', _depicts))

  def _image_url_from_sourceid(self, width=None):
    title = unquote(self.sourceid).replace(' ','_')
    md5 = hashlib.md5(title.encode('utf-8')).hexdigest()
    extension = title.split('.')[-1]
    img_url = f'https://upload.wikimedia.org/wikipedia/commons/{"thumb/" if width else ""}'
    img_url += f'{md5[:1]}/{md5[:2]}/{quote(title)}'
    if width:
      img_url = f'{img_url}/{width}px-{quote(title)}'
      if extension == 'svg': img_url += '.png'
      elif extension == 'tif' or extension == 'tiff': img_url += '.jpg'
    return img_url

  def _image_info(self, url):
    return self.raw_props['wc_metadata']['imageinfo'][0]

  def _service_endpoint(self):
    '''
    resp = requests.get(f'https://zoomviewer.toolforge.org/proxy.php?iiif={self.sourceid.replace(".tif",".jpg")}/info.json')
    if resp.status_code == 200:
      info_json = resp.json()
      logger.debug(json.dumps(info_json, indent=2))
      return info_json['@id'].replace('http','https')
    '''
    return f'https://zoomviewer.toolforge.org/proxy.php?iiif={self.sourceid.replace(".tif",".jpg")}'

  @property
  def raw_props(self):
    if self._raw_props is None:
      props = {}
      props['wc_metadata'] = self._get_wc_metadata(self.sourceid )
      if 'pageid' in props['wc_metadata']:
        props['wc_entity'] = self._get_wc_entity(props['wc_metadata']['pageid'])
        dro_qid = self._digital_representation_of(props['wc_entity'])
        props['dro_entity'] = self._get_wd_entity(dro_qid) if dro_qid else None
      self._raw_props = props
    logger.info(json.dumps(self._raw_props, indent=2))
    return self._raw_props
