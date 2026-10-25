#!/usr/bin/env python3
"""Download individually licensed WAV/OGG/FLAC Wikimedia Commons examples,
resample to 8 kHz mono signed PCM16 and record checksums/provenance.
Run on your own machine with internet connection; sources not included in bundle.
"""
import argparse, hashlib, json, pathlib, subprocess, urllib.parse, urllib.request, time
HERE=pathlib.Path(__file__).resolve().parent
HEADERS={'User-Agent':'MicroMusic-AudioBench/1.0 (academic local comparison; sample manifest in archive)'}

def download(entry,directory):
  # Wikimedia API URL is canonical per file; using Commons does not require guessed upload paths.
  title='File:'+entry['commons_filename']
  params=urllib.parse.urlencode({'action':'query','format':'json','prop':'imageinfo','iiprop':'url','titles':title})
  api='https://commons.wikimedia.org/w/api.php?'+params
  with urllib.request.urlopen(urllib.request.Request(api,headers=HEADERS),timeout=45) as r:
    response=json.load(r)
  info=next(iter(response['query']['pages'].values()))['imageinfo'][0]
  url=info['url']
  raw=directory/(entry['id']+pathlib.Path(urllib.parse.urlsplit(url).path).suffix)
  if not raw.exists():
    with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=90) as r,raw.open('wb') as out:
      import shutil;shutil.copyfileobj(r,out)
  pcm=directory/(entry['id']+'_8k_mono.wav')
  cmd=['ffmpeg','-hide_banner','-nostdin','-loglevel','error','-y','-i',str(raw), '-ar','8000','-ac','1','-c:a','pcm_s16le',str(pcm)]
  subprocess.run(cmd,check=True)
  return {'name':entry['id'],'original_url':url,'source_page':entry['page'],'author':entry['author'],'license':entry['license'],
          'original_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'pcm16_sha256':hashlib.sha256(pcm.read_bytes()).hexdigest(),
          'source_file':str(raw),'wav8k':str(pcm),'date_fetched':time.strftime('%Y-%m-%d')}

def main():
  ap=argparse.ArgumentParser()
  ap.add_argument('--category',choices=['all','ru_speech','en_speech','music'],default='all')
  ap.add_argument('--output',type=pathlib.Path,default=HERE/'external_samples')
  ap.add_argument('--dry-run',action='store_true')
  args=ap.parse_args()
  manifest=json.loads((HERE/'OPEN_SAMPLES.json').read_text())
  args.output.mkdir(exist_ok=True,parents=True)
  results=[]
  for src in manifest:
    if args.category!='all' and src['category']!=args.category:continue
    print(src['title'],src['page'],src['license'])
    if args.dry_run:continue
    try:results.append(download(src,args.output))
    except Exception as exc:print('FAILED',src['id'],str(exc))
  if results:(args.output/'provenance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
