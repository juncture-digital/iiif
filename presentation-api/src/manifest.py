#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import json
from urllib.parse import urlparse

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

import handlers.default
import handlers.edison_papers
import handlers.flickr
import handlers.github
import handlers.harvard_art_museums
import handlers.internet_archive
import handlers.jstor
import handlers.met
import handlers.openverse
import handlers.wikidata_images
import handlers.wikimedia_commons

_handlers = {
  'cc': handlers.openverse.Handler,
  'edison': handlers.edison_papers.Handler,
  'flickr': handlers.flickr.Handler,
  'gh': handlers.github.Handler,
  'harvard': handlers.harvard_art_museums.Handler,
  'ia': handlers.internet_archive.Handler,
  'jstor': handlers.jstor.Handler,
  'met': handlers.met.Handler,
  'wc': handlers.wikimedia_commons.Handler,
  'wd': handlers.wikidata_images.Handler
}

def get_manifest(mid, **kwargs):
  source, sourceid = mid.split(':',1) if ':' in mid else (None, mid)
  if source in _handlers:
    return _handlers[source](sourceid, **kwargs).get_manifest()
  else:
    return handlers.default.Handler(sourceid, **kwargs).get_manifest()

def manifest_url(url, baseurl):
  for _, handler in _handlers.items():
    if handler.can_handle(url):
      return handler.manifest_url(url, baseurl)
  if handlers.default.Handler.can_handle(url):
    return handlers.default.Handler.manifest_url(url, baseurl)
  else:
    parsed_url = urlparse(url)
    if parsed_url.netloc == 'archive.org' and parsed_url.path.startswith('/details'):
      resource_id = parsed_url.path.split('/')[2]
      return f'https://iiif.archivelab.org/iiif/{resource_id}/manifest.json'
  return url

def _find_item(obj, type, attr=None, attr_val=None, sub_attr=None):
  if 'items' in obj and isinstance(obj['items'], list):
    for item in obj['items']:
      if item.get('type') == type and (attr is None or (item.get(attr) == attr_val or attr_val is None)):
          return item[sub_attr] if sub_attr else item
      return _find_item(item, type, attr, attr_val, sub_attr)

def checkImageData(manifest):
  # logger.info(json.dumps(manifest, indent=2))
  canvas = _find_item(manifest, 'Canvas')
  if 'width' not in canvas or canvas['width'] is None:
    image_data = _find_item(manifest, type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    if image_data:
      svc = image_data['service'][0]
      resp = requests.get(f'{svc.get("@id", svc.get("id"))}/info.json')
      if resp.status_code == 200:
        info_json = resp.json()
        width = info_json.get('width')
        height = info_json.get('height')
        logger.info(f'width={width} height={height}')
    canvas['width'] = width
    canvas['height'] = height
    image = _find_item(manifest, type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    if image:
      image['width'] = width
      image['height'] = height
  return manifest

def main():
  manifest = get_manifest('gh:rdsnyder/images/italy-2022/amalfi-coast/Amalfi__1.jpg')
  # manifest = get_manifest('gh:kent-map/images/Barrets_Fire_2021.jpg')
  print(json.dumps(manifest, indent=2))
  
if __name__ == '__main__':
  main()