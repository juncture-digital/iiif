#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
BASEDIR = os.path.dirname(SCRIPT_DIR)

import hashlib
import re
from urllib.parse import quote

from handlers.handler_base import HandlerBase
from licenses import CreativeCommonsLicense, RightsStatement

class Handler(HandlerBase):

  @staticmethod
  def can_handle(url):
    return url.startswith('https://www.wikidata.org')

  @staticmethod
  def sourceid_from_url(url):
    return url.split('/')[-1]

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'wd:{sourceid.replace("?","%3F").replace("&","%26")}'
  
  def __init__(self, sourceid, **kwargs):
    self._raw_props = None
    super().__init__('wd', sourceid, **kwargs)

  def init_manifest(self):
    props = self.raw_props
    if self.external_manifest_url : return

    imageinfo = props['wc_metadata']['imageinfo'][0]
    extmetadata = imageinfo['extmetadata']
    
    self.image_url = self._image_url_from_sourceid()

    self.label = self._extract_text(extmetadata['ObjectName']['value']) if 'ObjectName' in extmetadata else None
    self.summary = self._extract_text(extmetadata['ImageDescription']['value']) if 'ImageDescription' in extmetadata else None

    # thumbnail width scaled to long side
    width = imageinfo['width']
    height = imageinfo['height']
    thumbnail_width = 240 if height > width else int(240 * width/height)
    self.width = width
    self.height = height
    self.format = imageinfo['mime']
    self.thumbnail = self._image_url_from_sourceid(thumbnail_width)
    
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
  
    if 'wc_entity' in props and props['wc_entity'] is not None:
      _dro = self._digital_representation_of(props['wc_entity'])
      if _dro:
        self.add_metadata('digital representation of', _dro)
      
    _depicts = list(set([self.sourceid] + [item['id'] for item in self._depicts(props['wd_entity'])]))
    self.add_metadata('depicts', _depicts)
  
  @property
  def raw_props(self):
    if not self._raw_props:
      props = {}
      props['wd_entity'] = self._get_wd_entity(self.sourceid)
      if 'P6108' in props['wd_entity']['claims']:
        self.external_manifest_url = props['wd_entity']['claims']['P6108'][0]['mainsnak']['datavalue']['value']
        logger.info(f'manifest={self.external_manifest_url}')
      else:
        title = self._wc_image_title()
        if title:
          props['title'] = title
          props['wc_metadata'] = self._get_wc_metadata(title)
          props['wc_entity'] = self._get_wc_entity(props['wc_metadata']['pageid'])
      self._raw_props = props
    return self._raw_props

  def _image_url_from_sourceid(self, width=None):
    title = self.raw_props["title"]
    logger.info(f'title={title}')
    md5 = hashlib.md5(title.encode('utf-8')).hexdigest()
    extension = title.split('.')[-1]
    img_url = f'https://upload.wikimedia.org/wikipedia/commons/{"thumb/" if width else ""}'
    img_url += f'{md5[:1]}/{md5[:2]}/{quote(title)}'
    if width:
      img_url = f'{img_url}/{width}px-{title}'
      if extension == 'svg': img_url += '.png'
      elif extension == 'tif' or extension == 'tiff': img_url += '.jpg'
    return img_url

  def _wc_image_title(self):
    entity = self._get_wd_entity(self.sourceid)
    image_statement = entity['claims']['P18'] if 'P18' in entity['claims'] else None
    if image_statement:
      image_statement = image_statement[0] if isinstance(image_statement,list) else [image_statement]
      return image_statement['mainsnak']['datavalue']['value'].replace(' ','_') if image_statement else ''
    #else:
    #  return 'Wikidata-logo.svg'

  def _service_endpoint(self):
    return f'https://zoomviewer.toolforge.org/proxy.php?iiif={self.raw_props["title"].replace(".tif",".jpg")}'
