#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

import os, sys, json
from time import time as now

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.append(SCRIPT_DIR)
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

from starlette.responses import RedirectResponse

import manifest_v2
from prezi_upgrader import Upgrader
from manifest import get_manifest, manifest_url, checkImageData

from media_info import MediaInfo

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

from expiringdict import ExpiringDict
_cache = ExpiringDict(max_len=100, max_age_seconds=3600)

app = FastAPI(title='Juncture IIIF Presentation API', root_path='/')

app.add_middleware(
  CORSMiddleware,
  allow_origins=['*'],
  allow_methods=['*'],
  allow_headers=['*'],
  allow_credentials=True,
)

@app.get('/docs/')
def docs():
  return RedirectResponse(url='/docs')

@app.get('/{path:path}/manifest.json')
@app.get('/iiif/{path:path}/manifest.json')
@app.get('/iiif/{version:int}/{path:path}/manifest.json')
def manifest(
    request: Request, 
    path: str, 
    refresh: Optional[str] = None,
    version: Optional[int] = 3
  ):
  start = now()
  refresh = refresh in ('', 'true')
  baseurl = f'{request.base_url.scheme}://{request.base_url.netloc}'
  manifest = get_manifest(path, baseurl=baseurl, refresh=refresh)
  logger.info(f'manifest: path={path} baseurl={baseurl} refresh={refresh} elapsed={round(now()-start,3)}')
  if version == 2:
    manifest = manifest_v2.convert(manifest, baseurl)
  return manifest

@app.post('/manifest/')
async def get_or_create_manifest(request: Request):
  start = now()
  payload = await request.body()
  payload = json.loads(payload)
  manifest = manifest_v2.get_manifest(**payload)
  logger.info(f'manifest: payload={payload} elapsed={round(now()-start,3)}')
  return manifest

@app.get('/manifest/{mid}/')
@app.get('/manifest/{mid}')
async def get_v2_manifest(
    mid: str, 
    refresh: Optional[bool] = False,
  ):
  v2_manifest = manifest_v2.get_manifest_by_id(mid, refresh)
  '''
  upgrader = Upgrader(flags={
    'crawl': False,        # NOT YET IMPLEMENTED. Crawl to linked resources, such as AnnotationLists from a Manifest
    'desc_2_md': True,     # If true, then the source's `description` properties will be put into a `metadata` pair. If false, they will be put into `summary`.
    'related_2_md': False, # If true, then the `related` resource will go into a `metadata` pair. If false, it will become the `homepage` of the resource.
    'ext_ok': False,       # If true, then extensions are allowed and will be copied across.
    'default_lang': 'en',  # The default language to use when adding values to language maps.
    'deref_links': False,  # If true, the conversion will dereference external content resources to look for format and type.
    'debug': False,        # If true, then go into a more verbose debugging mode.
    'attribution_label': '', # The label to use for requiredStatement mapping from attribution
    'license_label': ''} # The label to use for non-conforming license URIs mapped into metadata
  )
  v3_manifest = upgrader.process_resource(v2_manifest, True) 
  v3_manifest = upgrader.reorder(v3_manifest)
  return checkImageData(v3_manifest)
  '''
  return v2_manifest

@app.get('/gp-proxy/{path:path}')
async def gh_proxy(request: Request, response: Response, path: str):
  logger.info(f'gh_proxy: path={path} method={request.method}')
  gp_url = f'https://plants.jstor.org/seqapp/adore-djatoka/resolver?url_ver=Z39.88-2004&svc_id=info:lanl-repo/svc/getRegion&svc_val_fmt=info:ofi/fmt:kev:mtx:jpeg2000&svc.format=image/jpeg&rft_id=/{path}'
  if request.method in ('HEAD',):
    resp = requests.get(gp_url, headers = {'User-Agent': 'JSTOR Labs'})
    _cache[gp_url] = resp.content
    if resp.status_code == 200:
      response.headers['Content-Length'] = str(len(resp.content))
      response.headers['Content_Length'] = str(len(resp.content))
      return Response(status_code=204, media_type='image/jpeg')
  else:
    '''
    content = _cache.get(gp_url)
    if content is None:
      resp = requests.get(gp_url, headers = {'User-Agent': 'JSTOR Labs'})
      if resp.status_code == 200:
        content = resp.content
    if content:
      response.headers['Content-Length'] = str(len(content))
      return Response(content=content, status_code=200, media_type='image/jpeg')
    '''
    return RedirectResponse(url=gp_url)

@app.get('/prezi2to3/')
@app.post('/prezi2to3/')
async def prezi2to3(request: Request, manifest: Optional[str] = None):
  if request.method == 'GET':
    input_manifest = requests.get(manifest).json()
  else:
    body = await request.body()
    input_manifest = json.loads(body)
  manifest_version = 3 if 'http://iiif.io/api/presentation/3/context.json' in input_manifest.get('@context') else 2
  if manifest_version == 3:
    v3_manifest = input_manifest
  else:
    upgrader = Upgrader(flags={
      'crawl': False,        # NOT YET IMPLEMENTED. Crawl to linked resources, such as AnnotationLists from a Manifest
      'desc_2_md': True,     # If true, then the source's `description` properties will be put into a `metadata` pair. If false, they will be put into `summary`.
      'related_2_md': False, # If true, then the `related` resource will go into a `metadata` pair. If false, it will become the `homepage` of the resource.
      'ext_ok': False,       # If true, then extensions are allowed and will be copied across.
      'default_lang': 'en',  # The default language to use when adding values to language maps.
      'deref_links': False,  # If true, the conversion will dereference external content resources to look for format and type.
      'debug': False,        # If true, then go into a more verbose debugging mode.
      'attribution_label': '', # The label to use for requiredStatement mapping from attribution
      'license_label': ''} # The label to use for non-conforming license URIs mapped into metadata
    )
    v3_manifest = upgrader.process_resource(input_manifest, True) 
    v3_manifest = upgrader.reorder(v3_manifest)
  
  return checkImageData(v3_manifest)

def _metadata_value(manifest, key):
  return next(iter([list(md['value'].values())[0][0] for md in manifest.get('metadata',[]) if key in [list(md['label'].values())[0][0]]]), None)

def _find_item(obj, type, attr=None, attr_val=None, sub_attr=None):
  if 'items' in obj and isinstance(obj['items'], list):
    for item in obj['items']:
      if item.get('type') == type and (attr is None or item.get(attr) == attr_val):
          return item[sub_attr] if sub_attr else item
      return _find_item(item, type, attr, attr_val, sub_attr)

@app.get('/thumbnail/{path:path}')
@app.get('/thumbnail/')
@app.get('/thumbnail')
@app.get('/thumbnail')
@app.get('/banner/{path:path}')
@app.get('/banner/')
@app.get('/banner')
@app.get('/poster/{path:path}')
async def thumbnail(
  request: Request,
  path: Optional[str] = None,
  url: Optional[str] = None,
  refresh: Optional[bool] = False,
  region: Optional[str] = 'full',
  size: Optional[str] = None,
  width: Optional[int] = 0,
  height: Optional[int] = 0,
  rotation: Optional[int] = 0,
  time: Optional[int] = 0,
  quality: Optional[str] = 'default',
  format: Optional[str] = 'jpg'
  ):
  _type = [pe for pe in request.url.path.split('/') if pe][0]
  logger.info(f'thumbnail: path={path} url={url} type={_type}')
  if path:
      baseurl = f'{request.base_url.scheme}://{request.base_url.netloc}'
      manifest = get_manifest(path, baseurl=baseurl, refresh=refresh)
      logger.info(manifest)
      if _type == 'thumbnail':
        image_data = _find_item(manifest, type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
        if image_data.get('type') == 'Video':
          video_url = _metadata_value(manifest, 'image_url')
          thumbnail_url = MediaInfo().poster(url=video_url, time=time, refresh=refresh)
        else:
          image_data = _find_item(manifest, type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
          # thumbnail_url = manifest['thumbnail'][0]['id']
          if not width and not height and not size:
            width = 400
          _size = f'{width or size or ""},{height or size or ""}'
          thumbnail_url = f'{image_data["service"][0]["id"]}/{region}/{_size}/{rotation}/{quality}.{format}'
      else:
        image_data = _find_item(manifest, type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
        if 'service' in image_data:
          thumbnail_url = f'{image_data["service"][0]["id"]}/full/1000,/0/default.jpg'
        else: # banner
          thumbnail_url = manifest['thumbnail'][0]['id']
  else:
    ext = [elem for elem in url.split('/') if elem][-1].split('.')[-1]
    if ext in ('mp4', 'webm', 'ogg', 'ogv'): # is video
      thumbnail_url = MediaInfo().poster(url=url, time=time, refresh=refresh)
    else:
      thumbnail_url = manifest_v2.thumbnail(**{
        'url': url,
        'refresh': refresh,
        'region': region,
        'size': size,
        'width': width,
        'height': height,
        'rotation': rotation,
        'quality': quality,
        'format': format,
        'type': _type
      })
  # return Response(content=f'<a href="{thumbnail_url}"><img src="{thumbnail_url}" /></a>', status_code=200, media_type='text/html')
  return RedirectResponse(url=thumbnail_url)

@app.get('/mediainfo')
async def mediainfo(url):
  content, status_code = MediaInfo()(url=url)
  return Response(content=json.dumps(content), status_code=status_code, media_type='application/json')

@app.get('/')
async def default(
  request: Request,
  url: Optional[str] = None
  ):
  if url:
    baseurl = f'{request.base_url.scheme}://{request.base_url.netloc}'
    html = manifest_url(url, baseurl)
  else:
    html = open(f'{SCRIPT_DIR}/index.html', 'r').read()
  return Response(content=html, media_type='text/html')

if __name__ == '__main__':
  app.run(debug=True, host='0.0.0.0', port=8088)
else:
  from mangum import Mangum
  handler = Mangum(app)
