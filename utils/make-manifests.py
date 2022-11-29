#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
logging.basicConfig(format='%(asctime)s : %(levelname)s :  %(name)s : %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.WARNING)

import os, sys, getopt, traceback, time
from datetime import datetime

import json
import requests
import traceback
logging.getLogger('requests').setLevel(logging.WARNING)

sys.path.append('/opt/lib')

import os
import sys
import re
import getopt
from urllib.parse import quote, unquote, urlparse

import markdown as markdown_parser

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))

default_workbook = 'plant-humanities-image-inventory'
default_worksheet = 'metadata'

import gspread
from gspread.cell import Cell
from oauth2client.service_account import ServiceAccountCredentials

logging.getLogger('oauth2client.client').setLevel(logging.WARNING)
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']

iiif_service_endpoint = 'https://iiif.juncture-digital.org/manifest/'

ignore_fields = {'ready', 'essay', 'thumbnail', 'manifest', 'iiif-url', 'width', 'height', 'format'}

strip_html_regex = re.compile(r'<[^>]+>')

def get_workbook(workbook=default_workbook, **kwargs):
    logger.info(f'get_workbook: {workbook}')
    creds_file = f'{SCRIPT_DIR}/gs-creds.json'
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
    client = gspread.authorize(creds)
    return client.open(workbook)

def format_fields(metadata):
    for field in ('title', 'label', 'description', 'attribution'):
        if field in metadata:
            formatted_val = markdown_parser.markdown(metadata[field], output_format='html5').replace('<p>','').replace('</p>','')
            if formatted_val != metadata[field]:
                metadata[f'{field}_formatted'] = formatted_val
                metadata[field] = strip_html_regex.sub('', formatted_val)
    return metadata

def create_manifest(iiif_service=iiif_service_endpoint, dryrun=False, **kwargs):
    logger.debug(f'create_manifest: service_endpoint={iiif_service} dryrun={dryrun} kwargs={kwargs}')
    # data = {**dict([(f,kwargs[f]) for f in kwargs if f not in ignore_fields and kwargs[f]]), **{'iiif': True,}}
    data = dict([(f,kwargs[f]) for f in kwargs if f not in ignore_fields and kwargs[f]])
    data = format_fields(data)
    data['url'] = data['url'].replace(' ', '%20')
    if dryrun:
        logger.info(json.dumps(data, indent=2))
    else:
        resp = requests.post(iiif_service, headers={'Content-type': 'application/json'}, json=data)
        if resp.status_code == 200:
            return resp.json()
        else:
            logger.warning(f'{resp.status_code} {resp.content}')

def get_manifest(url):
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.json()

def get_thumbnail(manifest):
    thumbnail = None
    if 'thumbnail' in manifest:
        thumbnail = manifest['thumbnail']['@id'] if isinstance(manifest['thumbnail'],dict) else manifest['thumbnail']
    else:
        try:
            logger.debug(json.dumps(manifest['sequences'][0]['canvases'][0], indent=2))
            if manifest['sequences'][0]['canvases'][0]['thumbnail']:
                thumbnail = manifest['sequences'][0]['canvases'][0]['thumbnail']['@id']
        except:
            pass
        if thumbnail is None:
            try:
                thumbnail = manifest['sequences'][0]['canvases'][0]['images'][0]['resource']['@id'].replace('/full/full/0/default', '/full/150,/0/default')
            except:
                pass
    logger.debug(f'thumbnail={thumbnail}')                    
    return thumbnail

def as_hyperlink(qid, label=None):
    return '=HYPERLINK("{}", "{}")'.format('https://kg.jstor.org/entity/{}'.format(qid), label if label else qid)

def as_image(url):
    return f'=IMAGE("{url}")'

def is_ready(rec):
    return rec.get('ready').lower() in ('x', 't', 'true', 'y', 'yes')

def usage():
    print(('%s [hl:w:s:i:r:n]' % sys.argv[0]))
    print('   -h --help            Print help message')
    print('   -l --loglevel        Logging level (default=warning)')
    print('   -w --workbook        Workbook name (default="%s")' % default_workbook)
    print('   -s --worksheet       Worksheet name (default="%s")' % default_worksheet)
    print('   -i --iiif-service    IIIF service endpoint (default="%s")' % iiif_service_endpoint)
    print('   -r --row             Row to process')
    print('   -n --dryrun          Run script without updating worksheet')

if __name__ == '__main__':
    logger.setLevel(logging.WARNING)
    kwargs = {}
    try:
        opts, args = getopt.getopt(
            sys.argv[1:], 'hl:w:s:i:r:n', ['help', 'loglevel', 'workbook', 'worksheet', 'iiif-service', 'row', 'dryrun'])
    except getopt.GetoptError as err:
        # print help information and exit:
        logger.info(str(err))  # will print something like "option -a not recognized"
        usage()
        sys.exit(2)

    for o, a in opts:
        if o in ('-l', '--loglevel'):
            loglevel = a.lower()
            if loglevel in ('error',): logger.setLevel(logging.ERROR)
            elif loglevel in ('warn','warning'): logger.setLevel(logging.INFO)
            elif loglevel in ('info',): logger.setLevel(logging.INFO)
            elif loglevel in ('debug',): logger.setLevel(logging.DEBUG)
        elif o in ('-w', '--workbook'):
            kwargs['workbook'] = a
        elif o in ('-s', '--worksheet'):
            kwargs['worksheet'] = a
        elif o in ('-i', '--iiif-service'):
            kwargs['iiif-service'] = a
        elif o in ('-r', '--row'):
            kwargs['row'] = int(a)
        elif o in ('-n', '--dryrun'):
            kwargs['dryrun'] = True
        elif o in ('-h', '--help'):
            usage()
            sys.exit()
        else:
            assert False, "unhandled option"

    dryrun = kwargs.pop('dryrun', False)
    row_to_process = kwargs.pop('row') if 'row' in kwargs else None
    iiif_service = kwargs.pop('iiif-service', iiif_service_endpoint)

    logger.info(f'iiif-service={iiif_service}')

    worksheets = {}
    ws_data = {}
    wb = get_workbook(**kwargs)
    logger.debug(kwargs.get('worksheet', default_worksheet))
    ws = wb.worksheet(kwargs.get('worksheet', default_worksheet))
    rows = ws.get_all_values()
    fields = rows[0]
    field_idx = dict([(fields[i], i) for i in range(len(fields))])
    recs = [dict([(fields[col], row[col]) for col in range(len(row))]) for row in rows[1:]]

    updates = []
    for i, rec in enumerate(recs):
        row = i + 2
        if (row_to_process is None and is_ready(rec)) or (row_to_process == row):
            is_updated = False
            try:
                if rec['manifest']:
                    manifest = get_manifest(rec['manifest'])
                else:
                    manifest = create_manifest(iiif_service, **rec, dryrun=dryrun)
                if manifest:
                    logger.debug(json.dumps(manifest, indent=2))
                    img = manifest['sequences'][0]['canvases'][0]['images'][0]['resource']
                    thumbnail_url = get_thumbnail(manifest)
                    logger.info('service' in img)
                    if 'service' in img and thumbnail_url:
                        row_updates = {
                            'manifest': manifest['@id'],
                            'thumbnail': as_image(thumbnail_url),
                            'iiif-url': img['service']['@id'],
                            'height': img['height'],
                            'width': img['width'],
                            'format': img['format'].split('/')[-1],
                            'ready': ''
                        }
                        updates += [Cell(row, field_idx[fld] + 1, val) for fld, val in row_updates.items() if fld in field_idx]
                        is_updated = True
            except KeyboardInterrupt:
                break
            except:
                logger.warning(traceback.format_exc())
                logger.debug(json.dumps(manifest, indent=2))
            logger.info(f'processed row={row} updated={is_updated}')
    if updates:
        updates.sort(key=lambda cell: cell.col, reverse=False)
        ws.update_cells(updates, value_input_option='USER_ENTERED')
