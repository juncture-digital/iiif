#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

import os
import yaml

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG = yaml.load(open(f'{SCRIPT_DIR}/config.yaml', 'r').read(), Loader=yaml.FullLoader)

import sys
from hashlib import sha256
import json
import getopt
from urllib.parse import urlparse

from pymongo import MongoClient

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

from s3 import Bucket
manifest_cache = Bucket('iiif-manifest-cache')
thumbnail_cache = Bucket('iiif-thumbnail')

import boto3
SQS_URL = 'https://sqs.us-east-1.amazonaws.com/804803416183/iiif-convert'

PLACEHOLDER_IMAGE = 'https://upload.wikimedia.org/wikipedia/commons/e/e0/PlaceholderLC.png'

def _queue_iiif_convert(image_url):
    logger.info(f'queue_iiif_convert: image_url={image_url}')
    return boto3.client('sqs').send_message(
        QueueUrl=SQS_URL,
        DelaySeconds=0,
        MessageAttributes={'url': {'DataType': 'String', 'StringValue': image_url}},
        MessageBody=json.dumps({'url': image_url})
    )['MessageId']

def _image_service():
    # return 'https://4x4rr42s5yd4hr7mdrjqp3euqm0hnpoe.lambda-url.us-east-1.on.aws/iiif/2'
    return 'https://iiif-image.juncture-digital.org/iiif/2'

def _image_id(image_url):
    return sha256(image_url.encode('utf-8')).hexdigest()

def _info_json(image_url):
    info_json_url = f'{_image_service()}/{_image_id(image_url)}/info.json'
    logger.info(f'_info_json: url={info_json_url} id={_image_id(image_url)}')
    resp = requests.get(info_json_url)
    return resp.json() if resp.status_code == 200 else {}

def _info_json_exists(image_url):
    info_json_url = f'{_image_service()}/{_image_id(image_url)}/info.json'
    return requests.head(info_json_url).status_code == 200

def _service_endpoint(image_url):
    if not _info_json_exists(image_url):
        _queue_iiif_convert(image_url)
    return f'{_image_service()}/{_image_id(image_url)}'

def _metadata(**kwargs):
    md = []
    for prop in kwargs:
        if prop == 'navDate':
            md.append({ 'label': prop, 'value': kwargs['navDate'] })
        elif prop == 'url':
            md.append({ 'label': 'image-source-url', 'value': kwargs[prop] })
        else:
            md.append({ 'label': prop, 'value': kwargs[prop] })
    return md

def _make_manifest_v2_1_1(mid, **kwargs):
    '''Create an IIIF presentation v2.1.1 manifest'''
    manifest = {
        '@context': 'http://iiif.io/api/presentation/2/context.json',
        '@id': f'{{BASE_URL}}/manifest/{mid}',
        '@type': 'sc:Manifest',
        'label': kwargs.get('label', '')  ,
        'metadata': _metadata(**kwargs),
        'sequences': [{
            '@id': f'{{BASE_URL}}/sequence/{mid}',
            '@type': 'sc:Sequence',
            'canvases': [{
                '@id': f'{{BASE_URL}}/canvas/{mid}',
                '@type': 'sc:Canvas',
                'label': kwargs.get('label', ''),
                'height': 3000,
                'width': 3000,
                'images': [{
                    '@type': 'oa:Annotation',
                    'motivation': 'sc:painting',
                    'resource': {
                        '@id': kwargs['url'],
                    },
                    'on': f'{{BASE_URL}}/canvas/{mid}'
                }]
            }]
        }]
    }

    for prop in kwargs:
        if prop.lower() in ('attribution', 'description', 'label', 'license', 'logo', 'navDate'):
            manifest[prop.lower()] = kwargs[prop]
            if prop.lower() == 'label':
                manifest['sequences'][0]['canvases'][0]['label'] = kwargs[prop]

    return manifest

def _add_image_data(manifest, image_data):
    if image_data and 'service' in image_data:
        manifest['sequences'][0]['canvases'][0]['width'] = image_data['width']
        manifest['sequences'][0]['canvases'][0]['height'] = image_data['height']
        manifest['sequences'][0]['canvases'][0]['images'][0]['resource'].update({
            '@type': 'dcTypes:Image',
            'format': 'image/jpeg',
            'height': image_data['height'],
            'width': image_data['width'],
            'service': {
                '@context': 'http://iiif.io/api/image/2/context.json',
                '@id': image_data['service'],
                'profile': 'http://iiif.io/api/image/2/level2.json'
            }
        })
        manifest['thumbnail'] = f'{image_data["service"]}/full/150,/0/default.jpg'
    return manifest

def _image_url(url):
    _url = urlparse(url)
    if _url.netloc == 'github.com' and 'raw=true' in _url.query:
        path_elems = [elem for elem in _url.path.split('/') if elem]
        acct, repo, _, ref = path_elems[:4]
        path = '/'.join(path_elems[4:])
        logger.debug(f'GitHub image: hostname={_url.hostname} acct={acct} repo={repo} ref={ref} path={path}')
        return f'https://raw.githubusercontent.com/{acct}/{repo}/{ref}/{path}'
    else:
        return url

def _get_image_data(image_url):
    logger.debug(f'_get_image_data: url={image_url}')
    image_data = _info_json(image_url)
    if image_data:
        image_data['service'] = _service_endpoint(image_url)
    else:
        _queue_iiif_convert(image_url)
    return image_data

def get_manifest(**kwargs):
    baseurl = 'https://iiif.juncture-digital.org'
    image_url = _image_url(kwargs['url'])
    mid = sha256(image_url.encode()).hexdigest()
    is_updated = False

    manifest = manifest_cache.get(mid)
    if manifest:
        if not isinstance(manifest, str):
            manifest = manifest.decode('utf-8')
        manifest = json.loads(manifest)    
    else:
        manifest = _make_manifest_v2_1_1(mid, **kwargs)
        is_updated = True
    
    if 'service' not in manifest['sequences'][0]['canvases'][0]['images'][0]['resource']:
        _add_image_data(manifest, _get_image_data(image_url))
        is_updated = True

    serialized_manifest = json.dumps(manifest)
    if is_updated:
        manifest_cache[mid] = serialized_manifest
    return json.loads(serialized_manifest.replace('{BASE_URL}', baseurl))

_db_connection = None
def connect_db():
    '''MongoDB connection'''
    global _db_connection
    atlas_endpoint = f'mongodb+srv://{CONFIG["atlas"]}/?retryWrites=true&w=majority'

    if _db_connection is None:
        _db_connection = MongoClient(atlas_endpoint)['iiif']
    return _db_connection

def get_manifest_by_id(id):
    baseurl = 'https://iiif.juncture-digital.org'
    cached_manifest = manifest_cache.get(id)
    if cached_manifest and not isinstance(cached_manifest, str):
        cached_manifest = cached_manifest.decode('utf-8')
    if cached_manifest:
       manifest = json.loads(cached_manifest.replace('{BASE_URL}', baseurl))
    else:
        # try to get manifest from legacy MongoDB database
        mdb = connect_db()
        manifest = mdb['manifests'].find_one({'_id': id})
        if manifest:
            # cache MongoDB manifest locally
            del manifest['_id']
            service =  manifest['sequences'][0]['canvases'][0]['images'][0]['resource'].get('service')
            if service is None or 'iiifhosting.com' in service['@id']:
                image_url = manifest['sequences'][0]['canvases'][0]['images'][0]['resource']['@id']
                _queue_iiif_convert(image_url)
                manifest['sequences'][0]['canvases'][0]['images'][0]['resource']['service'] = {
                    '@context': 'http://iiif.io/api/image/2/context.json',
                    '@id': _service_endpoint(image_url),
                    'profile': 'http://iiif.io/api/image/2/level2.json'
                }
                manifest['thumbnail'] = f'{_service_endpoint(image_url)}/full/150,/0/default.jpg'
                mid = sha256(image_url.encode()).hexdigest()
                manifest_cache[mid] = json.dumps(manifest)
    return manifest

def _calc_region_and_size(**kwargs):

    width = height = None

    if kwargs.get('size'):
        size = kwargs['size'].replace('x',',').replace('X',',')
        if ',' not in size:
            size = f'{size},'
        width, height = [int(arg) if arg.isdecimal() else None for arg in size.split(',')]
    else:
        if 'width' in kwargs and int(kwargs['width']) > 0: width = int(kwargs['width'])
        if 'height' in kwargs and int(kwargs['height']) > 0: height = int(kwargs['height'])

    _type = kwargs.get('type','thumbnail')
    if width is None and height is None:
        width = 400 if _type == 'thumbnail' else 1000
        height = 260 if _type == 'thumbnail' else 400
        size = f'!{width},{height}'
    elif width is not None:
        size = f'{width},'
    elif height is not None:
        size = f',{height}'

    return kwargs.get('region', 'full'), size

def _create_presigned_url(bucket_name, object_name, expiration=600):
  boto3.setup_default_session()
  # Generate a presigned URL for the S3 object
  s3_client = boto3.client(
    's3',
    region_name='us-east-1',
    config=boto3.session.Config(signature_version='s3v4',)
  )
  try:
    response = s3_client.generate_presigned_url(
      'get_object',
      Params={'Bucket': bucket_name, 'Key': object_name},
      ExpiresIn=expiration
    )
  except Exception as e:
      print(e)
      logging.error(e)
      return 'Error'
  return response

def thumbnail(refresh=False, **kwargs):
    thumbnail_id = sha256(''.join([f'{key}={kwargs[key]}' for key in sorted(kwargs)]).encode('utf-8')).hexdigest()
    
    if not refresh and thumbnail_id in thumbnail_cache:
        return _create_presigned_url('iiif-thumbnail', thumbnail_id)
    
    image_url = _image_url(kwargs['url'])
    image_data = _get_image_data(image_url)
    if image_data:
        is_placeholder = False
    else:
        _queue_iiif_convert(image_url)
        image_data = _get_image_data(PLACEHOLDER_IMAGE)
        is_placeholder = True
    region, size = _calc_region_and_size(**kwargs)
    thumbnail_url = f'{image_data["service"]}/{region}/{size}/{kwargs["rotation"]}/{kwargs["quality"]}.{kwargs["format"]}'    
    resp = requests.get(thumbnail_url)
    if resp.status_code == 200:
        if not is_placeholder: thumbnail_cache[thumbnail_id] = resp.content
        thumbnail_url = _create_presigned_url('iiif-thumbnail', thumbnail_id)
    return thumbnail_url

def _find_item(obj, type, attr=None, attr_val=None, sub_attr=None):
    if 'items' in obj and isinstance(obj['items'], list):
        for item in obj['items']:
            if item.get('type') == type and (attr is None or item.get(attr) == attr_val):
                return item[sub_attr] if sub_attr else item
            return _find_item(item, type, attr, attr_val, sub_attr)

def _lang_map_value(item):
    return (item['en'] if 'en' in item else item['none'] if 'none' in item else item[list(item.keys())[0]])[0]

def convert(v3_manifest, baseurl, **kwargs):
    mid = '/'.join(v3_manifest['id'].split('/')[3:-1])
    label = _lang_map_value(v3_manifest['label'])
    image_info = _find_item(v3_manifest, type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    manifest = {
        '@context': 'http://iiif.io/api/presentation/2/context.json',
        '@id': f'{{BASE_URL}}/iiif/2/{mid}/manifest.json',
        '@type': 'sc:Manifest',
        'label': label,
        'sequences': [{
            '@id': f'{{BASE_URL}}/sequence/{mid}',
            '@type': 'sc:Sequence',
            'canvases': [{
                '@id': f'{{BASE_URL}}/canvas/{mid}',
                '@type': 'sc:Canvas',
                'label': label,
                'height': image_info['height'],
                'width': image_info['width'],
                'images': [{
                    '@id': f'{{BASE_URL}}/annotation/{mid}',
                    '@type': 'oa:Annotation',
                    'motivation': 'sc:painting',
                    'resource': {
                        '@id': image_info['id'],
                        '@type': 'dctypes:Image',
                        'format': 'image/jpeg',
                        'height': image_info['height'],
                        'width': image_info['width'],
                        'service': {
                            '@context': 'http://iiif.io/api/image/2/context.json',
                            '@id': image_info['service'][0]['id'],
                            'profile': 'http://iiif.io/api/image/2/level2.json'
                        }
                    },
                    'on': f'{{BASE_URL}}/canvas/{mid}'
                }]
            }]
        }],
        'thumbnail': {'@id' : f'{image_info["service"][0]["id"]}/full/150,/0/default.jpg'}
    }
    
    if 'summary' in v3_manifest:
        manifest['description'] = _lang_map_value(v3_manifest['summary'])

    if 'rights' in v3_manifest:
        manifest['license'] = v3_manifest['rights']

    if 'navDate' in v3_manifest:
        manifest['navDate'] = v3_manifest['navDate']

    if 'requiredStatement' in v3_manifest:
        manifest['attribution'] = _lang_map_value(v3_manifest['requiredStatement']['value'])

    if 'metadata' in v3_manifest and len(v3_manifest['metadata']) > 0:
        manifest['metadata'] = [{'label': _lang_map_value(md['label']), 'value': _lang_map_value(md['value'])} for md in v3_manifest['metadata']]

    manifest = json.loads(json.dumps(manifest).replace('{BASE_URL}', baseurl))
    return manifest

def usage():
    print('%s [hl:a:d:n:r:b:p:t] url' % sys.argv[0])
    print('   -h --help         Print help message')
    print('   -l --loglevel     Logging level (default=warning)')
    print('   -a --attribution  Image attribution')
    print('   -d --description  Image description')
    print('   -n --label        Image label')
    print('   -r --license      Image license')
    print('   -b --logo         Image logo')
    print('   -p --navDate      Image navDate')
    print('   -t --dryrun       Use for testing')

if __name__ == '__main__':
    kwargs = {}
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hl:a:d:n:r:b:p:t', ['help', 'loglevel', 'attribution', 'description', 'label', 'license', 'logo', 'navDate', 'dryrun'])
    except getopt.GetoptError as err:
        # print help information and exit:
        print(str(err)) # will print something like "option -a not recognized"
        usage()
        sys.exit(2)

    for o, a in opts:
        if o in ('-l', '--loglevel'):
            loglevel = a.lower()
            if loglevel in ('error',): logger.setLevel(logging.ERROR)
            elif loglevel in ('warn','warning'): logger.setLevel(logging.INFO)
            elif loglevel in ('info',): logger.setLevel(logging.INFO)
            elif loglevel in ('debug',): logger.setLevel(logging.DEBUG)
        elif o in ('-a', '--attribution'):
            kwargs['attribution'] = a
        elif o in ('-d', '--description'):
            kwargs['description'] = a
        elif o in ('-n', '--label'):
            kwargs['label'] = a
        elif o in ('-r', '--license'):
            kwargs['license'] = a
        elif o in ('-b', '--logo'):
            kwargs['logo'] = a
        elif o in ('-p', '--navDate'):
            kwargs['navDate'] = a
        elif o in ('-t', '--dryrun'):
            kwargs['dryrun'] = True
        elif o in ('-h', '--help'):
            usage()
            sys.exit()
        else:
            assert False, 'unhandled option'
    
    if len(args) > 0:
        kwargs['url'] = args[0]
        print(json.dumps(get_manifest(**kwargs)))
    else:
        usage()
