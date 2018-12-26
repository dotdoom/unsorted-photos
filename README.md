# Unsorted Photos

Find Google Photos pictures which are not added to any album yet, and print out
their URLs.

## Install

```shell
$ pip install -r requirements.txt
```

## Configure

1. Create a [Google Cloud project](https://console.cloud.google.com/projectcreate).

1. Enable [Photos Library API](https://console.developers.google.com/apis/library/photoslibrary.googleapis.com)
   for that project.

1. [Create OAuth Client ID](https://console.cloud.google.com/apis/credentials/wizard?api=photoslibrary.googleapis.com)
   calling API from "Other UI", accessing "User data". OAuth Client ID allows
   the application to impersonate a Google user when accessing Google APIs,
   given explicit user approval.

1. Download JSON file for the Client ID and put it next to the script.

1. [Quota for Photos API](https://console.cloud.google.com/apis/api/photoslibrary.googleapis.com/quotas)
   is 10,000 calls per day at the moment of writing this.

## Usage

```shell
$ ./photos.py -h
```

or

```shell
> photos.py
```

## Performance

The script is completely stateless and does not store neither credentials nor
any lists of pictures. Therefore it has to request credentials at every run.

A typical run on an average computer with ~10k pictures and ~200 albums, with a
very fast Internet connection takes up to 20 min.
