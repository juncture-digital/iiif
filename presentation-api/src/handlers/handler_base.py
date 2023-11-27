import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import json
import hashlib
from urllib.parse import quote
from time import time as now
from datetime import datetime
from hashlib import sha256

# from image_info import ImageInfo
from media_info import MediaInfo

import requests
logging.getLogger('requests').setLevel(logging.WARNING)

from bs4 import BeautifulSoup

from s3 import Bucket

import boto3
SQS_URL = 'https://sqs.us-east-1.amazonaws.com/804803416183/iiif-convert'

entity_labels = {}
manifest_cache = Bucket('iiif-manifest-cache')

from expiringdict import ExpiringDict
wd_entities = ExpiringDict(max_len=100, max_age_seconds=1800) # cache entities for 30 minutes
wc_entities = ExpiringDict(max_len=100, max_age_seconds=1800)
external_manifests = ExpiringDict(max_len=100, max_age_seconds=1800)

class HandlerBase(object):

  def __init__(self, source, sourceid, **kwargs):
    start = now()
    self.source = source
    self.sourceid = sourceid
    self.baseurl = kwargs.get('baseurl')
    self.language = kwargs.get('language', 'en')
    self.refresh = kwargs.get('refresh', False)
    self.is_updated = False
    self._image_url = None
    self._source_url = None
    self.external_manifest_url = False
  
    self.m = manifest_cache.get(self.manifestid) if not self.refresh else None

    logger.info(f'HandlerBase: source={self.source} sourceid={self.sourceid} baseurl={self.baseurl} cached={self.m is not None} refresh={self.refresh}')

    if self.m:
      self.m = json.loads(self.m.decode('utf-8') if isinstance(self.m, bytes) else self.m)
      days_since_last_update = None
      manifest_last_updated = next(iter([list(md['value'].values())[0][0] for md in self.m.get('metadata',[]) if 'updated' in [list(md['label'].values())[0][0]]]), None)
      if manifest_last_updated:
        manifest_last_updated = datetime.strptime(manifest_last_updated, '%Y-%m-%dT%H:%M:%SZ')
        days_since_last_update = (datetime.now() - manifest_last_updated).days
        logger.debug(f'manifest_last_updated={manifest_last_updated} days_since_last_update={days_since_last_update}')
      if days_since_last_update is None or days_since_last_update > 30:
        self.m = None

    if not self.m:
      self.m = {
        '@context': 'http://iiif.io/api/presentation/3/context.json',
        'id': f'{{BASE_URL}}/{self.manifestid}/manifest.json',
        'type': 'Manifest',
        'items': [{
          'type': 'Canvas',
          'id': f'{{BASE_URL}}/{self.manifestid}/canvas/p1',
          'items': [{
            'type': 'AnnotationPage',
            'id': f'{{BASE_URL}}/{self.manifestid}/p1/1',
            'items': [{
              'type': 'Annotation',
              'id': f'{{BASE_URL}}/{self.manifestid}/annotation/p0001-image',
              'motivation': 'painting',
              'target': f'{{BASE_URL}}/{self.manifestid}/canvas/p1',
              'body': {
                'id': self.image_url,
                'format': '',
              } 
            }]
          }]
        }]
      }
      self.init_manifest()
      if not self.external_manifest_url:
        self.add_metadata(self._language_map('updated', datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')))
        self.set_service()

        if self.image_url:
          related = self._get_related_entities()
          if related and 'P180' in related:
            self.add_metadata(self._language_map('depicts', [item['id'] for item in related['P180']]))

          manifest_cache[self.manifestid] = json.dumps(self.m)

    logger.debug(f'HandlerBase: elapsed={round(now()-start,3)}')

  @property
  def canvas(self):
    return self._find_item('Canvas')

  def get_image_url(self):
    return self._image_url
  
  def set_image_url(self, url):
    self._image_url = url
    logger.debug(f'image_url={self._image_url}')
    self.add_metadata('image_url', self._image_url)

  image_url = property(get_image_url, set_image_url)


  @property
  def manifestid(self):
    return f'{self.source}:{quote(self.sourceid)}' if self.source else self.sourceid

  def get_source_url(self):
    return self._source_url
  
  def set_source_url(self, url):
    self._source_url = url
    logger.debug(f'source_url={self._source_url}')
    self.add_metadata('source_url', self._source_url)

  source_url = property(get_source_url, set_source_url)

  def get_label(self):
    return self.m.get('label')
  
  def set_label(self, label):
    self.m['label'] = {self.language:[label]}
    body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    if 'format' in body and body['format'].startswith('image'):
      self.canvas['label'] = label
      body['label'] = label

  label = property(get_label, set_label)


  def get_summary(self):
    return self.m.get('summary')

  def set_summary(self, summary):
    self.m['summary'] = {self.language:[summary]}

  summary = property(get_summary, set_summary)


  def get_metadata(self):
    return self.m.get('metadata', [])

  def add_metadata(self, arg1, arg2=None):
    lm = arg1 if isinstance(arg1, dict) and arg2 is None else self._language_map(arg1, arg2)
    if not 'metadata' in self.m: self.m['metadata'] = []
    lm_labels = set([val for values in lm['label'].values() for val in values])
    if set(['depicts', 'digital representation of']).intersection(lm_labels):
      lm = self._link_qids(lm)
      idx, existing = self._find_metadata('depicts')
      if existing:
        lm = self._merge_language_maps(existing, lm)
      else:
        self.m['metadata'].append(lm)
    else:
      labels = list(set([val for values in lm['label'].values() for val in values]))
      idx, existing = self._find_metadata(labels[0])
      if existing:
        logger.debug(f'replacing metadata value: {lm}')
        self.m['metadata'][idx] = lm
      else:
        self.m['metadata'].append(lm)

  metadata = property(get_metadata)


  def get_rights(self):
    return self.m.get('rights')

  def set_rights(self, rights):
    self.m['rights'] = rights

  rights = property(get_rights, set_rights)


  def get_requiredStatement(self):
    return self.m.get('requiredStatement')

  def set_requiredStatement(self, statement):
    logger.debug(f'set_requiredStatement: {statement}')
    for attr in ('label', 'value'):
      if attr in statement and isinstance(statement[attr], str):
        statement[attr] = {self.language: [statement[attr]]}
    self.m['requiredStatement'] = statement

  requiredStatement = property(get_requiredStatement, set_requiredStatement)


  def get_provider(self):
    return self.m.get('provider')

  def set_provider(self, providers):
    if providers:
      self.m['provider'] = providers if isinstance(providers,list) else [providers]
    elif 'provider' in self.m:
      del self.m['provider']

  provider = property(get_provider, set_provider)


  def get_thumbnail(self):
    return self.m.get('thumbnail')

  def set_thumbnail(self, thumbnail):
    if isinstance(thumbnail, str):
      thumbnail = [{'id': thumbnail, 'type': 'Image'}]
    self.m['thumbnail'] = thumbnail

  thumbnail = property(get_thumbnail, set_thumbnail)


  def get_navDate(self):
    return self.m.get('navDate')

  def set_navDate(self, navDate):
    '''See https://iiif.io/api/presentation/3.0/#navdate
    The value must be an XSD dateTime literal. The value must have a timezone, 
    and should be given in UTC with the Z timezone indicator, but may instead be 
    given as an offset of the form +hh:mm.'''
    self.m['navDate'] = navDate

  navDate = property(get_navDate, set_navDate)


  def set_homepage(self, homepage):
    self.m['homepage'] = homepage

  def set_logo(self, logo):
    self.m['logo'] = logo


  def get_format(self):
    body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    return body.get('format')

  def set_format(self, format):
    if format:
      body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
      body['format'] = format
      _type = 'Sound' if format == 'application/ogg' else format.split('/')[0].replace('audio','Sound').title()
      self.set_type(_type)

  format = property(get_format, set_format)
  
  def get_type(self):
    body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    return body.get('type')

  def set_type(self, _type):
    if _type:
      body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
      body['type'] = _type

  type = property(get_type, set_type)

  def get_height(self):
    body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    return body['height'] if body else None

  def set_height(self, height):
    if height:    
      body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
      body['height'] = height
      self.canvas['height'] = height
  
  height = property(get_height, set_height)

  def get_width(self):
    body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    return body.get('width')

  def set_width(self, width):
    if width:
      body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
      body['width'] = width
      self.canvas['width'] = width
  
  width = property(get_width, set_width)

  def get_duration(self):
    body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    return body.get('duration')

  def set_duration(self, duration):
    if duration:
      body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
      body['duration'] = duration
      self.canvas['duration'] = duration
  
  duration = property(get_duration, set_duration)

  def _language_map(self, label, value):
    if not isinstance(label,list): label = [label]
    if not isinstance(value,list): value = [value]
    value = [str(val) for val in value]
    return {'label': {self.language: label}, 'value': {self.language: value}}

  def _merge_language_maps(self, lm1, lm2):
    merged = {'label': lm1['label'], 'value': lm1['value']}
    for lang in merged['value']:
      if lang in lm2['value']:
        for val in lm2['value'][lang]:
          if val not in merged['value'][lang]:
            merged['value'][lang].append(val)
    # logger.info(json.dumps(merged, indent=2))
    return merged

  def _find_metadata(self, label, lang=None):
    lang = lang or self.language
    for idx, md in enumerate(self.m.get('metadata', [])):
      if lang in md['label'] and label in md['label'][lang]:
        return idx, md
    return -1, None

  def _link_qids(self, lm):
    lm_values = set([val for values in lm['value'].values() for val in values])
    qids = [qid for qid in lm_values if qid[0] == 'Q' and qid[1:].isdigit()]
    if qids:
      labels_needed = [qid for qid in qids if qid not in entity_labels]
      if labels_needed:
        entity_labels.update(self.get_entity_labels(labels_needed, self.language))
      for lang in lm['value']:
        lm['value'][lang] = [f'<a href="https://www.wikidata.org/wiki/{qid}">{entity_labels.get(qid,qid)}</a>' for qid in lm['value'][lang]]
    return lm

  _cached_media_info = None
  def _media_info(self, url):
    if not self._cached_media_info:
      self._cached_media_info = MediaInfo()(url=url)
    return self._cached_media_info

  def _find_item(self, type, attr=None, attr_val=None, sub_attr=None, obj=None):
    obj = obj or self.m
    if 'items' in obj and isinstance(obj['items'], list):
      for item in obj['items']:
        #logger.info(f'{type} {motivation} type={item.get("type")} motivation={item.get("motivation")}')
        if item.get('type') == type and (attr is None or item.get(attr) == attr_val):
            return item[sub_attr] if sub_attr else item
        return self._find_item(type, attr, attr_val, sub_attr, item)

  def _queue_iiif_convert(self, quality=50, refresh=False):
    attrs = {'url': {'DataType': 'String', 'StringValue': self._image_url}}
    if refresh:
      attrs['refresh'] = {'DataType': 'String', 'StringValue': 'true'}
    if quality:
      attrs['quality'] = {'DataType': 'String', 'StringValue': str(quality)}
    logger.debug(attrs)
    boto3.client('sqs').send_message(
        QueueUrl=SQS_URL,
        DelaySeconds=0,
        MessageAttributes={
          'url': {'DataType': 'String', 'StringValue': self._image_url},
          'refresh': {'DataType': 'String', 'StringValue': 'true' if refresh else 'false'}
        },
        MessageBody=json.dumps(attrs)
    )
    image_id = sha256(self._image_url.encode('utf-8')).hexdigest()
    # info_json = f'https://4x4rr42s5yd4hr7mdrjqp3euqm0hnpoe.lambda-url.us-east-1.on.aws/iiif/2/{image_id}/info.json'
    info_json = f'https://iiif-image.juncture-digital.org/iiif/2/{image_id}/info.json'
    return info_json

  @property
  def _image_service(self):
    # return 'https://4x4rr42s5yd4hr7mdrjqp3euqm0hnpoe.lambda-url.us-east-1.on.aws/iiif/2'
    return 'https://iiif-image.juncture-digital.org/iiif/2'

  @property
  def _image_id(self):
    return sha256(self.image_url.encode('utf-8')).hexdigest()

  def _info_json_exists(self):
    info_json_url = f'{self._image_service}/{self._image_id}/info.json'
    return requests.head(info_json_url).status_code == 200

  def _service_endpoint(self):
    if self.refresh or not self._info_json_exists():
      self._queue_iiif_convert(refresh=self.refresh)
    return f'{self._image_service}/{self._image_id}'

  def set_service(self, refresh=False):        
    self.is_updated = True
            
    # if 'format' not in self.canvas:
    if not self.canvas.get('format'):
      _media_info, _ = self._media_info(self.image_url)
      logger.debug(json.dumps(_media_info, indent=2))
      for fld in ('duration', 'format', 'height', 'width'):
        if fld in _media_info: self.canvas[fld] = _media_info.get(fld,'')
      self.is_updated = True
      logger.debug(json.dumps(self.canvas, indent=2))
    
    body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
    for fld in ('duration', 'height', 'width'):
      if fld in self.canvas:
         body[fld] = self.canvas[fld]
    if 'format' in self.canvas:
      body['format'] = self.canvas['format']
      body['type'] = body['format'].split('/')[0].title()
      
    logger.debug(f'set_service: type={body.get("type")}')
    
    if body.get('type') == 'Image' and body.get('format') not in ('image/gif',):
      if refresh or self.refresh or 'service' not in body:
        endpoint = self._service_endpoint()
        # logger.info(f'set_service: endpoint={endpoint}')
        body['service'] = [{
          'id': endpoint,
          'profile': 'level2',
          'type': 'ImageService2'
        }]
        if 'thumbnail' not in self.m:
          self. m['thumbnail'] = [{'id': f'{endpoint}/full/150,/0/default.jpg', 'type': 'Image'}]
          self.is_updated = True
    body['id'] = self.image_url

    self.is_updated = True

  def get_entity_labels(self, qids, lang='en'):
    values = ' '.join([f'(<http://www.wikidata.org/entity/{qid}>)' for qid in qids])
    query = f'SELECT ?item ?label WHERE {{ VALUES (?item) {{ {values} }} ?item rdfs:label ?label . FILTER (LANG(?label) = "{lang}" || LANG(?label) = "en") .}}'
    resp = requests.get(
      f'https://query.wikidata.org/sparql?query={quote(query)}',
      headers = {
        'Content-Type': 'application/x-www-form-urlencoded', 
        'Accept': 'application/sparql-results+json',
        'User-Agent': 'Labs Client'
      }
    )
    if resp.status_code == 200:
      return dict([(rec['item']['value'].split('/')[-1],rec['label']['value']) for rec in resp.json()['results']['bindings']])
  
  def is_attribution_required(self):
    return 'rights' in self.m and 'creativecommons.org/licenses/by' in self.m['rights']

  def has_attribution_statement(self):
    labels = [label.lower() for labels in self.m.get('requiredStatement', {}).get('label',{'':[]}).values() for label in labels]
    values = [value for values in self.m.get('requiredStatement', {}).get('value',{'':[]}).values() for value in values]
    logger.debug(f'labels={labels} values={values}')
    return 'attribution' in labels

  def _get_related_entities(self):
    hash = hashlib.sha256(self.image_url.encode('utf-8')).hexdigest()
    query = f'_id:"{hash}"'
    resp = requests.post(
      'https://www.jstor.org/api/labs-search-service/labs/about/',
      headers = {
        'User-Agent': 'Labs client',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      json = {'query': {'query_string': {'query': query}}, 'size': 100}
    )
    logger.debug(f'get_related_entities: {query} {resp.status_code}')
    related = {}
    if resp.status_code == 200:
      results = resp.json()
      # logger.info(json.dumps(results,indent=2))
      for doc in results.get('hits',{}).get('hits',[]):
        for prop in doc['_source']['statements']:
          if doc['_source']['statements'][prop][0]['mainsnak']['datavalue']['type'] == 'wikibase-entityid':
            related[prop] = []
            for stmt in doc['_source']['statements'][prop]:
              related[prop].append({
                'id': stmt['mainsnak']['datavalue']['value']['id']['value'],
                'prominent': stmt['mainsnak']['datavalue']['value']['id']['rank'] == 'preferred'
              })
    return related

  def _qid_link(self, qid, labels):
    return f'<a id="{qid}" data-qid="{qid}" href="https://www.wikidata.org/entity/{qid}">{labels.get(qid,qid)}</a>'

  def _extract_text(self, val, lang='en'):
    soup = BeautifulSoup(val, 'html5lib')
    _elem = soup.select_one(f'[lang="{lang}"]')
    return (_elem.text if _elem else soup.text).strip()

  def _get_wc_metadata(self, title):
    url = f'https://commons.wikimedia.org/w/api.php?format=json&action=query&titles=File:{quote(title)}&prop=imageinfo&iiprop=extmetadata|size|mime'
    resp = requests.get(url)
    logger.debug(f'{url} {resp.status_code}')
    if resp.status_code == 200:
      return list(resp.json()['query']['pages'].values())[0]

  def _get_wc_entity(self, pageid):
    if pageid not in wc_entities:
      url = f'https://commons.wikimedia.org/wiki/Special:EntityData/M{pageid}.json'
      resp = requests.get(url)
      logger.debug(f'get_wc_entity: url={url} status={resp.status_code}')
      if resp.status_code == 200:
        wc_entities[pageid] = resp.json()['entities'][f'M{pageid}']
    return wc_entities.get(pageid)

  def _get_wd_entity(self, qid):
    if qid not in wd_entities:
      resp = requests.get(f'https://www.wikidata.org/wiki/Special:EntityData/{qid}.json')
      if resp.status_code == 200:
        results = resp.json()
        if qid in results['entities']:
          wd_entities[qid] = results['entities'][qid]
    return wd_entities.get(qid)

  def _digital_representation_of(self, entity):
    if entity:
      statements = entity['statements'] if 'statements' in entity else entity['claims']
      for prop in ('P6243', 'P921'):
        if prop in statements:
          return statements[prop][0]['mainsnak']['datavalue']['value']['id']
    return []

  def _depicts(self, entity):
    if entity:
      statements = entity['statements'] if 'statements' in entity else entity['claims']
      _depicts = [{'id': stmt['mainsnak']['datavalue']['value']['id'], 'prominent': stmt['rank'] == 'preferred'} for stmt in statements['P180']] if 'P180' in statements else []
      return sorted(_depicts, key = lambda i: i['prominent'], reverse=True)
    return []
  
  def _coords(self, entity):
    if entity:
      statements = entity['statements'] if 'statements' in entity else entity['claims']
      if 'P1259' in statements:
        val = statements['P1259'][0]['mainsnak']['datavalue']['value']
        return f'{val["latitude"]},{val["longitude"]}'

  def get_manifest(self):
    if self.external_manifest_url:
      if self.external_manifest_url not in external_manifests:
        external_manifests[self.external_manifest_url] = requests.get(self.external_manifest_url).json()
      return external_manifests[self.external_manifest_url]
    else:
      manifest = json.loads(json.dumps(self.m).replace('{BASE_URL}', self.baseurl))
      '''
      if self.source == 'wc':
        body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
        if body.get('type') == 'Image' and body.get('format') not in ('image/gif',):
          if 'service' not in body or 'zoomviewer.toolforge.org' in body['service'][0]['id']:
            self.image_url = self._image_url_from_sourceid()
            self.set_service(refresh=True)
            manifest = json.loads(json.dumps(self.m).replace('{BASE_URL}', self.baseurl))
      '''
      body = self._find_item(type='Annotation', attr='motivation', attr_val='painting', sub_attr='body')
      
      if 'type' not in body and 'id' in body:
        self.image_url = body['id']
        self.set_service(refresh=True)
        manifest = json.loads(json.dumps(self.m).replace('{BASE_URL}', self.baseurl))
        manifest_cache[self.manifestid] = json.dumps(self.m)
  
      # logger.info(json.dumps(manifest, indent=2))
      return manifest