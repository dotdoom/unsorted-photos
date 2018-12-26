#!/usr/bin/env python2

from __future__ import print_function

import argparse
import glob
import json
import os
import sys
import urllib

from requests_oauthlib import OAuth2Session

def parse_args():
  parser = argparse.ArgumentParser(
      description='Find Google Photos pictures which are not added to any '
      'album yet, and print out their URLs')
  parser.add_argument(
      '--include-archived',
      help='include archived photos',
      action='store_true',
  )
  parser.add_argument(
      '--oauth2-secret',
      help='file name containing OAuth2 client_id, downloaded from GCP console',
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
    params = {}

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
    for item in self._iterate(self.BASE_URL + '/albums', params={},
        listKey='albums'):
      yield item

  def sharedAlbums(self):
    for item in self._iterate(self.BASE_URL + '/sharedAlbums', params={},
        listKey='sharedAlbums'):
      yield item


def fail(message):
  print(message, file=sys.stderr)
  os.exit(1)


args = parse_args()

oauth2_secret_file = args.oauth2_secret
if oauth2_secret_file is None:
  for oauth2_secret_file in glob.glob('*.json'):
    print('No OAuth2 secret file specified, using', oauth2_secret_file)
    break
if oauth2_secret_file is None:
  fail('OAuth2 secret file not found')

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

sys.stdout.write('Collecting all pictures... ')
sys.stdout.flush()
libraryItems = {
    item['id']: item
    for item in photos.mediaItems()
}
libraryItemIds = set(libraryItems.keys())
sys.stdout.write('%d\n' % len(libraryItems))

sys.stdout.write('Collecting albums... ')
sys.stdout.flush()
albums = list(photos.albums())
sys.stdout.write('Shared albums... ')
sys.stdout.flush()
albums += list(photos.sharedAlbums())
sys.stdout.write('%d\n' % len(albums))

itemIdsInAllAlbums = set()

print('Finding items not belonging to any album.')
for album in albums:
  itemIdsInAlbum = {item['id'] for item in photos.mediaItems(album['id'])}
  itemIdsInAllAlbums |= itemIdsInAlbum

  print('%40s %s [%4d/%4d] %s' % (
    album.get('title', '*** NO TITLE ***'),
    '*' if 'shareInfo' in album else ' ',
    len(itemIdsInAlbum.intersection(libraryItemIds)),
    len(itemIdsInAlbum),
    album['productUrl'],
  ))
  if int(album.get('mediaItemsCount', 0)) != len(itemIdsInAlbum):
    print(
        '  WARNING: Number of items we got from this album (%d) does not\n'
        '           match the number of items reported by server (%r)' % (
          len(itemIdsInAlbum), album.get('mediaItemsCount')))


itemIdsNotInAlbum = libraryItemIds - itemIdsInAllAlbums
print('%d items are not in any album' % len(itemIdsNotInAlbum))
# TODO(dotdoom): print date, and sort by date.
for itemId in itemIdsNotInAlbum:
  item = libraryItems[itemId]
  print('%20s %s' % (
    item['mimeType'],
    item['productUrl'],
  ))
