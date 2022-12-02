#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
import logging
logging.basicConfig(format='%(asctime)s : %(filename)s : %(levelname)s : %(message)s')
logger = logging.getLogger()

import os
SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

import traceback
import yaml
import json
from datetime import datetime

from gh import gh_repo_info, get_gh_file, get_gh_last_commit, gh_user_info, get_default_branch, gh_dir_list

from handlers.handler_base import HandlerBase

from time import time as now
import concurrent.futures

class Handler(HandlerBase):

  rights = {
    # Creative Commons Licenses
    'CC0': {'label': 'Public Domain Dedication', 'url': 'http://creativecommons.org/publicdomain/zero/1.0/'},
    'CC-BY': {'label': 'Attribution', 'url': 'http://creativecommons.org/licenses/by/4.0/'},
    'CC-BY-SA': {'label': 'Attribution-ShareAlike', 'url': 'http://creativecommons.org/licenses/by-sa/4.0/'},
    'CC-BY-ND': {'label': 'Attribution-NoDerivs', 'url': 'http://creativecommons.org/licenses/by-nd/4.0/'},
    'CC-BY-NC': {'label': 'Attribution-NonCommercial', 'url': 'http://creativecommons.org/licenses/by-nc/4.0/'},
    'CC-BY-NC-SA': {'label': 'Attribution-NonCommercial', 'url': 'http://creativecommons.org/licenses/by-nc-sa/4.0/'},
    'CC-BY-NC-ND': {'label': 'Attribution-NonCommercial-NoDerivs', 'url': 'http://creativecommons.org/licenses/by-nc-nd/4.0/'},
    
    # Rights Statements 
    'InC': {'label': 'IN COPYRIGHT', 'url': 'http://rightsstatements.org/vocab/InC/1.0/'},
    'InC-OW-EU': {'label': 'IN COPYRIGHT - EU ORPHAN WORK', 'url': 'http://rightsstatements.org/vocab/InC-OW-EU/1.0/'},
    'InC-EDU': {'label': 'IN COPYRIGHT - EDUCATIONAL USE PERMITTED', 'url': 'http://rightsstatements.org/vocab/InC-EDU/1.0/'},
    'InC-NC': {'label': 'IN COPYRIGHT - NON-COMMERCIAL USE PERMITTED', 'url': 'http://rightsstatements.org/vocab/InC-NC/1.0/'},
    'InC-RUU': {'label': 'IN COPYRIGHT - RIGHTS-HOLDER(S) UNLOCATABLE OR UNIDENTIFIABLE', 'url': 'http://rightsstatements.org/vocab/InC-RUU/1.0/'},
    'NoC-CR': {'label': 'NO COPYRIGHT - CONTRACTUAL RESTRICTIONS', 'url': 'http://rightsstatements.org/vocab/NoC-CR/1.0/'},
    'NoC-NC': {'label': 'NO COPYRIGHT - NON-COMMERCIAL USE ONLY', 'url': 'http://rightsstatements.org/vocab/NoC-NC/1.0/'},
    'NoC-OKLR': {'label': 'NO COPYRIGHT - OTHER KNOWN LEGAL RESTRICTIONS', 'url': 'http://rightsstatements.org/vocab/NoC-OKLR/1.0/'},
    'NoC-US': {'label': 'NO COPYRIGHT - UNITED STATES', 'url': 'http://rightsstatements.org/vocab/NoC-US/1.0/'},
    'CNE': {'label': 'COPYRIGHT NOT EVALUATED', 'url': 'http://rightsstatements.org/vocab/CNE/1.0/'},
    'UND': {'label': 'COPYRIGHT UNDETERMINED', 'url': 'http://rightsstatements.org/vocab/UND/1.0/'},
    'NKC': {'label': 'NO KNOWN COPYRIGHT', 'url': 'http://rightsstatements.org/vocab/NKC/1.0/'}
  }

  @staticmethod
  def can_handle(url):
    return url.startswith('https://github.com') or url.startswith('https://raw.githubusercontent.com')

  @staticmethod
  def _fix_sourceid(sourceid):
    fname = sourceid.split('/')[-1]
    if '.' not in fname:
      acct, repo = sourceid.split('/')[:2]
      _dir = '/'.join(sourceid.split('/')[2:-1])
      for _file in gh_dir_list(acct, repo, _dir):
        if '.' in _file and _file.split('.')[0] == fname:
          sourceid += f'.{_file.split(".")[1]}'
          break
    return sourceid

  @staticmethod
  def sourceid_from_url(url):
    path = [elem for elem in url.split('/') if elem != ''][2:]
    if 'raw.githubusercontent.com' in url:
      sourceid = '/'.join(path[:2] + path[3:])
    else:
      sourceid = '/'.join(path[:2] + path[4:])
    return sourceid

  @staticmethod
  def manifest_url(url, baseurl):
    sourceid = Handler.sourceid_from_url(url)
    return f'gh:{sourceid.replace("?","%3F").replace("&","%26")}'
  
  def __init__(self, sourceid, **kwargs):
    super().__init__('gh', Handler._fix_sourceid(sourceid), **kwargs)

  def init_manifest(self):
    props = self.raw_props
    ref = props['repo_info']['default_branch']
    logger.debug(json.dumps(['gh_props'], indent=2))
    self._update_props(props['gh_props'])

    sourceid_elems = self.sourceid.split('/')
    last_sourceid_elem = sourceid_elems[-1]

    label = props['gh_props'].get('label') or last_sourceid_elem.split('-')[0].split('__')[0].split('.')[0].replace('_', ' ')
    self.set_label(label)

    self.image_url = props['gh_props'].get('image_url') or self._image_url_from_sourceid()
    image_url_elems = self.image_url.split('/')
    self.source_url =  f'https://github.com/{sourceid_elems[0]}/{sourceid_elems[1]}/blob/{ref}/{"/".join(image_url_elems[6:])}'

    _media_info = self._media_info(self.image_url)
    for key in ('created', 'location', 'orientation', 'size'):
      if key in _media_info:
        self.add_metadata(key, str(_media_info[key]))

    if '-' in last_sourceid_elem:
      _rights_code = last_sourceid_elem.split('-',1)[1].split('.')[0]
      if _rights_code in self.rights:
        self.set_rights(self.rights[_rights_code]['url'])
    if 'rights' not in self.m:
      self.set_rights(self.rights['CC-BY']['url'])

    if self._image_is_self_hosted():
      if '-' in last_sourceid_elem:
        _rights_code = last_sourceid_elem.split('-',1)[1].split('.')[0]
        if _rights_code in self.rights:
          self.set_rights(self.rights[_rights_code]['url'])
      if 'rights' not in self.m:
        self.set_rights(self.rights['CC-BY']['url'])
      
      if self.is_attribution_required() and not self.has_attribution_statement():
        owner = f'<a href="{props["user_info"]["html_url"]}">{props["user_info"]["name"] or props["user_info"]["login"]}</a>'
        self.set_requiredStatement(self._language_map('attribution', f'Content provided by {owner} under <a href="https://creativecommons.org/licenses/by/4.0/">CC BY</a> license'))

    else:
      if not props['gh_props'].get('rights_defined_for_image'):
        self.set_rights(self.rights['UND']['url'])
      if not props['gh_props'].get('requiredStatement_defined_for_image'):
        self.set_requiredStatement(self._language_map('attribution', f'Content obtained from {self.image_url}'))
      self.provider = None

  def _image_is_self_hosted(self):
    gh_prefix = '/'.join(self.sourceid.split('/')[:2])
    image_path_prefix = '/'.join(self.image_url.split('/')[3:5])
    # image_host = '.'.join(self.image_url.split('/')[2].split('.')[-2:])
    image_host = self.image_url.split('/')[2]
    is_self_hosted = image_host in ('stor.artstor.org',) or (image_host in ('github.com', 'raw.githubusercontent.com') and gh_prefix == image_path_prefix)
    logger.debug(f'_image_is_self_hosted={is_self_hosted} gh_prefix={gh_prefix} image_host={image_host} image_path_prefix={image_path_prefix}')
    return is_self_hosted

  def _image_url_from_sourceid(self, ref=None):
    sourceid_elems = self.sourceid.split('/')
    acct, repo = sourceid_elems[:2]
    ref = ref if ref else get_default_branch(acct, repo)
    path = '/'.join(sourceid_elems[2:])
    return f'https://raw.githubusercontent.com/{acct}/{repo}/{ref}/{path}'

  def _update_props(self, props):
    for key, value in props.items():
      if key in ('service','rights_defined_for_image','requiredStatement_defined_for_image'): continue
      try:
        getattr(self, f'set_{key}')(value)
      except:
        logger.debug(traceback.format_exc())
        try:
          self.add_metadata(self._language_map(key, value))
        except:
          pass

  def _merge_gh_props(self, props):
    merged = {}
    for _props in [props[idx] for idx in sorted(props, reverse=True)]:
      for key, value in _props.items():
        if key == 'depicts':
          if not isinstance(value, list): value = [value]
          if 'depicts' not in merged:
            merged['depicts'] = value
          else:
            merged['depicts'] = [qid for qid in value if qid not in merged['depicts']] + merged['depicts']
        elif key == 'navDate':
          merged[key] = str(value)
        else:
          merged[key] = value
    image_props = props[0] if 0 in props else {}
    if 'rights' in image_props: merged['rights_defined_for_image'] = True
    if 'requiredStatement' in image_props: merged['requiredStatement_defined_for_image'] = True
    return merged

  def _get_gh_props(self, acct, repo, ref, image_path):
    path_elems = image_path.split('/')[2:]

    props_paths = [f'/{"/".join(path_elems).split(".")[0]}.yaml'] + [f'/{"/".join(path_elems[:-(i+1)])}{"/" if i < len(path_elems)-1 else ""}iiif-props.yaml' for i in range(len(path_elems))]
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(props_paths)) as executor:
      futures = {}
      for idx, path in enumerate(props_paths):
        futures[executor.submit(get_gh_file, acct, repo, ref, path)] = idx
      
      for future in concurrent.futures.as_completed(futures):
        idx = futures[future]
        try:
          results[idx] = yaml.load(future.result(), Loader=yaml.FullLoader) or {}
        except Exception as exc:
          logger.info('%r generated an exception: %s' % (props_paths[idx], exc))
          logger.debug(traceback.format_exc())
    logger.debug(json.dumps(results,indent=2))
    return self._merge_gh_props(results)

  @property
  def raw_props(self):
    props = {}
    acct, repo = self.sourceid.split('/')[:2]
    props['repo_info'] = gh_repo_info(acct, repo)
    props['user_info'] = gh_user_info(login=props['repo_info']['owner']['login'])
    ref = props['repo_info']['default_branch']
    props['gh_props'] = self._get_gh_props(acct, repo, ref, self.sourceid)
    return props

  def _last_updated(self):
    start = now()
    sourceid_path_elems = [elem for elem in self.sourceid.split('/') if elem.strip()]
    acct, repo = sourceid_path_elems[:2]
    repo_info = gh_repo_info(acct, repo)
    ref = repo_info['default_branch']

    # List of GH files to check
    file_path_elems =  sourceid_path_elems[2:]
    gh_paths = [f'{"/".join(file_path_elems).split(".")[0]}.yaml'] + [f'{"/".join(file_path_elems[:-(i+1)])}{"/" if i < len(file_path_elems)-1 else ""}iiif-props.yaml' for i in range(len(file_path_elems))]
    #if '.' in file_path_elems[-1] and file_path_elems[-1].split('.')[-1].lower() in ('jpg', 'jp2', 'jpeg', 'png'):
    #  gh_paths.append('/'.join(file_path_elems))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gh_paths)) as executor:
      futures = {}
      for path in gh_paths:
        futures[executor.submit(get_gh_last_commit, acct, repo, ref, path)] = path
      
      for future in concurrent.futures.as_completed(futures):
        path = futures[future]
        try:
          results[path] = future.result()
        except Exception as exc:
          logger.debug('%r generated an exception: %s' % (path, exc))

    dates = sorted([date for date in results.values() if date], reverse=True) if results else []
    last_update = dates[0].strftime('%Y-%m-%dT%H:%M:%SZ') if dates else None 
    logger.debug(f'_last_updated: last_update={last_update} elapsed={round(now()-start,3)}')
    return last_update
    
  def _is_current(self, m):
    sourceid = '/'.join(m['id'].split('/')[1:-1]).split(':',1)[1]
    manifest_last_updated = next(iter([list(md['value'].values())[0][0] for md in m.get('metadata',[]) if 'updated' in [list(md['label'].values())[0][0]]]), None)
    if manifest_last_updated:
      manifest_last_updated = datetime.strptime(manifest_last_updated, '%Y-%m-%dT%H:%M:%SZ')
      gh_last_updated = datetime.strptime(self._last_updated(), '%Y-%m-%dT%H:%M:%SZ')
    is_current = manifest_last_updated and gh_last_updated == manifest_last_updated
    logger.debug(f'_is_current: sourceid={sourceid} manifest_last_updated={manifest_last_updated} gh_last_updated={gh_last_updated} is_current={is_current}')
    return is_current
