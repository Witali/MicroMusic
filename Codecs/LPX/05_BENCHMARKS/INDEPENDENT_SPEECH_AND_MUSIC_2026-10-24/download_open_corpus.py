#!/usr/bin/env python3
"""Download independently documented source audio when external HTTPS is available.
No API keys. Resamples all sources to 8 kHz mono 16-bit WAV and records hashes.
This was NOT executed online in the original offline benchmark environment.
"""
import argparse,urllib.parse,urllib.request,subprocess,hashlib,json,datetime
from pathlib import Path
DATA={
 'ru_sayings':{'file':'Russian_sayings.ogg','author':'Юный Вадим','license':'PD-self','source':'https://commons.wikimedia.org/wiki/File:Russian_sayings.ogg'},
 'ru_intro':{'file':'Voice introduction of Siarhei Besarab (Russian).ogg','author':'Siarhei Besarab','license':'CC BY-SA 4.0','source':'https://commons.wikimedia.org/wiki/File:Voice_introduction_of_Siarhei_Besarab_(Russian).ogg'},
 'en_intro':{'file':'Greg Shapiro - voice - en -151127 184009.flac','author':'1Veertje','license':'CC0 1.0','source':'https://commons.wikimedia.org/wiki/File:Greg_Shapiro_-_voice_-_en_-151127_184009.flac'},
 'piano_goldberg':{'url':'https://soniqtools.com/assets/audio/test-audio-flac-16bit-44khz.flac','author':'Kimiko Ishizaka / Open Goldberg Variations','license':'CC0','source':'https://soniqtools.com/test-audio-files'},
}
HEAD={'User-Agent':'MicroMusic-LPX4-research/1.0 (personal audio codec quality evaluation)'}
def fetch(url,path):
 req=urllib.request.Request(url,headers=HEAD)
 with urllib.request.urlopen(req,timeout=80) as r,open(path,'wb') as w:
  while True:
   b=r.read(1024*64)
   if not b:break
   w.write(b)
def main():
 a=argparse.ArgumentParser();a.add_argument('--output',type=Path,default=Path('open_audio'));a.add_argument('--dry-run',action='store_true');opts=a.parse_args()
 opts.output.mkdir(exist_ok=True,parents=True);log=[]
 for key,e in DATA.items():
  if opts.dry_run:
   print(key,e['source'],e['license']);continue
  try:
   url=e.get('url')
   if not url:
    title='File:'+e['file'];api='https://commons.wikimedia.org/w/api.php?'+urllib.parse.urlencode({'action':'query','prop':'imageinfo','iiprop':'url','format':'json','titles':title})
    with urllib.request.urlopen(urllib.request.Request(api,headers=HEAD),timeout=50) as r:info=json.load(r)
    url=next(iter(info['query']['pages'].values()))['imageinfo'][0]['url']
   ext=Path(urllib.parse.urlparse(url).path).suffix
   raw=opts.output/(key+ext);wav=opts.output/(key+'_8k16_mono.wav')
   fetch(url,raw)
   subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(raw),'-t','30','-ac','1','-ar','8000','-c:a','pcm_s16le',str(wav)],check=True)
   res={**e,'id':key,'url':url,'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'pcm_sha256':hashlib.sha256(wav.read_bytes()).hexdigest(),'utc_download':datetime.datetime.now(datetime.timezone.utc).isoformat()}
   log.append(res);print('OK',key,raw.stat().st_size,'B')
  except Exception as exc:print('FAILED',key,str(exc))
 if log:(opts.output/'provenance.json').write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n')
if __name__=='__main__':main()
