#!/usr/bin/env python2

from __future__ import print_function

import argparse
import glob
import json
import os
import urllib
import webbrowser

from collections import defaultdict
from requests_oauthlib import OAuth2Session

def parse_args():
  parser = argparse.ArgumentParser(
      description='Find Google Photos pictures which are not added to any '
      'album yet, and print out their URLs')
  parser.add_argument(
      '--oauth2-secret',
      help='file name containing OAuth2 client_id, downloaded from GCP console',
  )
  parser.add_argument(
      '--browser-batch',
      help='number of non-album photos that should be opened in a browser at a '
      'time. Before opening each "batch" of unsorted photo URLs in the '
      'browser, the script will ask for confirmation. Set to 0 to disable '
      'browser prompts and just print photo URLs',
      type=int,
      default=25,
  )
  return parser.parse_args()


class PhotosError(Exception):
  pass


class Photos(object):

  BASE_URL = 'https://photoslibrary.googleapis.com/v1'
  NEXT_PAGE_TOKEN_KEY = 'nextPageToken'

  def __init__(self, session):
    self._session = session
    super(Photos, self).__init__()

  def _requestJSON(self, url, params=None, method='GET'):
    # TODO(dotdoom): wrap in try/catch and retry?
    if method == 'GET':
      if params:
        url += '?' + urllib.urlencode(params)
      response = self._session.get(url)
    else:
      response = self._session.post(url, data=params)

    # TODO(dotdoom): retry?
    if not response.headers['Content-Type'].startswith('application/json'):
      raise PhotosError(
          'Request %s has finished with HTTP code %d, but did not return data '
          'in JSON format:\n%s' % (url, response.status_code, response.content))

    json = response.json()

    if response.status_code != 200:
      status = json['error']['status']
      message = json['error']['message']
      raise PhotosError('Request %s finished with error: %d (%s):\n%s' % (
        url, response.status_code, status, message))

    return json

  def _iterate(self, url, params=None, method='GET', listKey=None):
    if params is None:
      params = {}
    else:
      params = params.copy()

    while 1:
      json = self._requestJSON(url, params=params, method=method)
      if not json:
        break

      data = json.get(listKey or list(
        set(json.keys()) - {self.NEXT_PAGE_TOKEN_KEY})[0])
      if data is None:
        raise PhotosError('No data key found, available keys: [%s]' %
            ', '.join(json.keys()))
      else:
        for item in data:
          yield item

      if self.NEXT_PAGE_TOKEN_KEY in json:
        params['pageToken'] = json[self.NEXT_PAGE_TOKEN_KEY]
      else:
        break

  def mediaItems(self, albumId=None):
    url = self.BASE_URL + '/mediaItems'
    method = 'GET'
    params = {
        # Setting higher values may help avoiding API calls quota too fast.
        # 100 is the maximum allowed by mediaItems API, according to doc.
        'pageSize': 100,
    }

    if albumId is not None:
      url += ':search'
      method = 'POST'
      params['albumId'] = albumId

    for item in self._iterate(url,
        params=params,
        method=method,
        listKey='mediaItems'):
      yield item

  def albums(self):
    params = {
        'pageSize': 50,
    }
    for item in self._iterate(self.BASE_URL + '/albums', params=params,
        listKey='albums'):
      yield item

  def sharedAlbums(self):
    params = {
        'pageSize': 50,
    }
    for item in self._iterate(self.BASE_URL + '/sharedAlbums', params=params,
        listKey='sharedAlbums'):
      yield item


args = parse_args()

oauth2_secret_file = args.oauth2_secret
if oauth2_secret_file is None:
  for oauth2_secret_file in glob.glob('*.json'):
    print('No OAuth2 secret file specified, using', oauth2_secret_file)
    break

with open(oauth2_secret_file, 'r') as f:
  oauth2_secret = json.load(f)

oauth2_secret = oauth2_secret.values()[0]
google = OAuth2Session(oauth2_secret['client_id'],
    scope=['https://www.googleapis.com/auth/photoslibrary'],
    redirect_uri=oauth2_secret['redirect_uris'][0])
authorization_url, state = google.authorization_url(oauth2_secret['auth_uri'],
    access_type='online',
    prompt='select_account')
print('Please authorize the script here:', authorization_url)
authorization_code = raw_input('Once authorized, please paste the value here:')
try:
  google.fetch_token(oauth2_secret['token_uri'],
      client_secret=oauth2_secret['client_secret'],
      code=authorization_code)
except:
  # In case we got a redirect to localhost instead of a code.
  google.fetch_token(oauth2_secret['token_uri'],
      client_secret=oauth2_secret['client_secret'],
      authorization_response=authorization_code)

photos = Photos(google)

print('Collecting all pictures...')
libraryItems = {
    item['id']: item
    for item in photos.mediaItems()
}
libraryItemIds = set(libraryItems.keys())
print('  Total: %d' % len(libraryItems))

print('Collecting albums...')
albums = list(photos.albums())
print('  Shared albums...')
albums += list(photos.sharedAlbums())
print('  Total: %d' % len(albums))

itemIdsInAllAlbums = set()
print('Finding items not belonging to any album.')
for album in albums:
  itemIdsInAlbum = {item['id'] for item in photos.mediaItems(album['id'])}
  itemIdsInAllAlbums |= itemIdsInAlbum

  # Interesting fact: album.mediaItemsCount would not always match
  # len(itemIdsInAlbum), but the latter usually matches Photos UI.

  print('%-40s %s [%4d/%4d] %s' % (
    album.get('title', '*** NO TITLE ***'),
    '*' if 'shareInfo' in album else ' ',
    len(itemIdsInAlbum.intersection(libraryItemIds)),
    len(itemIdsInAlbum),
    album['productUrl'],
  ))

itemsNotInAnyAlbum = sorted(
    [libraryItems[itemId] for itemId in libraryItemIds - itemIdsInAllAlbums],
    key=lambda item: item.get('mediaMetadata', {}).get('creationTime', ''))
print('%d items are not in any album, sorted by creation time (ascending)' %
    len(itemsNotInAnyAlbum))

class BrowserBatch(object):

  PROMPT = 'Would you like to open these %d items in browser [Y/n]? '

  def __init__(self, batch_size):
    self._batch_size = batch_size
    self._batch = []
    super(BrowserBatch, self).__init__()

  def add(self, url):
    if self._batch_size > 0:
      self._batch.append(url)
      if len(self._batch) == self._batch_size:
        self.open()

  def open(self):
    if self._batch:
      if raw_input(self.PROMPT % len(self._batch)).lower() != 'n':
        for url in self._batch:
          webbrowser.open(url)
    self._batch = []

browser_batch = BrowserBatch(args.browser_batch)
for item in itemsNotInAnyAlbum:
  metadata = item.get('mediaMetadata', defaultdict(str))
  print('%-32s %-15s %-11s %s' % (
    metadata['creationTime'],
    item['mimeType'],
    'x'.join((metadata['width'], metadata['height'])),
    item['productUrl'],
  ))
  browser_batch.add(item['productUrl'])

browser_batch.open()
