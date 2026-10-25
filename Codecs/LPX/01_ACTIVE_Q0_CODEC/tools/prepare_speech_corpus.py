#!/usr/bin/env python3
"""Fetch *optional* short open voice examples and prepare exact 8kHz PCM16 WAV.

Main corpora (Common Voice, LibriSpeech) are downloaded manually subject to
provider terms. This tool does not redistribute or infer speaker identity.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,urllib.request,urllib.parse,wave,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SAMPLES=ROOT/'samples'/'catalog.json'

def shell(cmd):
    r=subprocess.run(cmd,capture_output=True,text=True)
    if r.returncode:raise RuntimeError((r.stderr or r.stdout)[:900])

def convert(src,dst,max_seconds=10):
    if not shutil.which('ffmpeg'):raise RuntimeError('ffmpeg is required')
    dst.parent.mkdir(parents=True,exist_ok=True)
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(src),'-vn','-ac', '1','-ar','8000',
         '-c:a','pcm_s16le',str(dst)]
    shell(cmd)
    with wave.open(str(dst),'rb') as w:
        if (w.getnchannels(),w.getsampwidth(),w.getframerate())!=(1,2,8000):raise ValueError('output WAV mismatch')
        sec=w.getnframes()/8000
    if sec<.2 or sec>max_seconds:
        dst.unlink(missing_ok=True)
        raise ValueError(f'recording duration {sec:.2f}s is outside [0.2,{max_seconds}]')
    return sec

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--catalog',type=Path,default=SAMPLES)
    a.add_argument('--output',type=Path,default=ROOT/'samples'/'prepared')
    a.add_argument('--fetch-short',action='store_true',help='download 4 Commons originals; internet required')
    a.add_argument('--local-dir',type=Path,help='convert local WAV/OGG/MP3/FLAC clips (e.g. after downloading Common Voice)')
    a.add_argument('--max-seconds',type=float,default=10.)
    a.add_argument('--limit',type=int,default=30)
    opts=a.parse_args();opts.output.mkdir(parents=True,exist_ok=True)
    catalog=json.loads(opts.catalog.read_text(encoding='utf-8'));entries=[]
    if opts.fetch_short:
        for v in catalog['short_samples']:
            raw=opts.output/(v['id']+'.ogg')
            if not raw.exists():
                # Use Commons' file redirect (not a guessed content hash path).
                link='https://commons.wikimedia.org/wiki/Special:Redirect/file/'+urllib.parse.quote(v['original_filename'])
                req=urllib.request.Request(link,headers={'User-Agent':'MicroMusicCodecResearch/1.0 (personal offline audio analysis)'})
                try:
                    with urllib.request.urlopen(req,timeout=35) as r:raw.write_bytes(r.read())
                except Exception as e:
                    print(f'SKIP {v["id"]}: fetch failed: {e}');continue
            try:duration=convert(raw,opts.output/(v['id']+'_8k.wav'),opts.max_seconds)
            except (ValueError,RuntimeError) as e:print(f'SKIP {v["id"]}: {e}');continue
            entries.append({'id':v['id'],'lang':v['lang'],'path':str(opts.output/(v['id']+'_8k.wav')),
                            'speaker_group':v['speaker_group'],'duration_s':round(duration,3),
                            'attribution':v['attribution'],'license':v['license'],'source':v['source_page']})
    if opts.local_dir:
        paths=sorted(p for p in opts.local_dir.rglob('*') if p.is_file() and p.suffix.lower() in ('.wav','.flac','.mp3','.ogg','.opus'))[:opts.limit]
        for i,p in enumerate(paths):
            name=f'local_{i:03d}_{p.stem[:30]}'
            try:duration=convert(p,opts.output/(name+'.wav'),opts.max_seconds)
            except (ValueError,RuntimeError) as e:print(f'SKIP {p.name}: {e}');continue
            entries.append({'id':name,'lang':'unknown','path':str(opts.output/(name+'.wav')),
                            'duration_s':round(duration,3),'source_path':str(p),
                            'warning':'Set true language and speaker group before using split into train/test'})
    (opts.output/'prepared_manifest.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'prepared':len(entries),'manifest':str(opts.output/'prepared_manifest.json')},ensure_ascii=False))
if __name__=='__main__':main()
