#!/usr/bin/env python3
"""Acquire the exact upstream tarball and verify SHA256 (requires internet)."""
import urllib.request
import hashlib
from pathlib import Path
import argparse
SHA='4b44d4f2b38a370a2d98a78329fefc56a0cf93d1c1be70029217baae6628feea'
URLS=[
 'https://downloads.xiph.org/releases/speex/speex-1.2.1.tar.gz',
 'https://ftp.osuosl.org/pub/xiph/releases/speex/speex-1.2.1.tar.gz',
]
if __name__=='__main__':
  a=argparse.ArgumentParser()
  a.add_argument('--dest',default='speex-1.2.1.tar.gz')
  args=a.parse_args(); out=Path(args.dest)
  if out.exists():
    b=out.read_bytes()
  else:
    for url in URLS:
      try:
        print('Downloading',url)
        b=urllib.request.urlopen(url,timeout=30).read()
        break
      except Exception as e:
        print(type(e).__name__,e)
    else:
      raise SystemExit('Download failed. Supply official speex-1.2.1.tar.gz manually.')
  h=hashlib.sha256(b).hexdigest()
  if h != SHA:
    raise SystemExit(f'SHA256 mismatch: {h} != {SHA}; NOT saved')
  out.write_bytes(b)
  print('Verified',out,len(b),'bytes SHA256',h)
