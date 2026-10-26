#!/usr/bin/env python3
"""Split WB12.8 speech into Flash-sized demos with independent reset oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--corpus',type=Path,default=ROOT/'build/higher-corpus')
    p.add_argument('--out',type=Path,default=ROOT/'build/higher-player-corpus');p.add_argument('--frames',type=int,default=192);args=p.parse_args()
    if not 1<=args.frames<=192:p.error('Use 1..192 frames to leave room for the decoder in 32 KB Flash')
    out=args.out.resolve();(out/'streams').mkdir(parents=True,exist_ok=True);(out/'oracle').mkdir(exist_ok=True)
    source=json.loads((args.corpus/'manifest.json').read_text(encoding='utf-8'));rows=[]
    for item in source['streams']:
        if item['family']!='wb128' or not item['natural']:continue
        original=args.corpus/'wb128/streams'/item['stream'];assert digest(original)==item['inputSha256'];raw=original.read_bytes()
        step=args.frames*32
        for number,start in enumerate(range(0,len(raw),step)):
            data=raw[start:start+step];name=original.stem+f'-part{number:02d}'
            stream=out/'streams'/(name+'.spxraw');oracle=out/'oracle'/(name+'.pcm');stream.write_bytes(data)
            subprocess.run([ROOT/'build/wb-reference/decode.exe','1','32',stream,oracle],check=True)
            rows.append(dict(stream=stream.name,frames=len(data)//32,inputSha256=digest(stream),pcmSha256=digest(oracle),
                sourceStream=item['stream'],sourceSha256=item['inputSha256'],sourceFirstFrame=start//32,resetAtChunkStart=True))
    result=dict(packetBytes=32,frameSamples=320,sourceCorpusSha256=digest(args.corpus/'manifest.json'),streams=rows)
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PASS:',len(rows),'Flash-sized demos /',sum(r['frames'] for r in rows),'frames; each oracle starts from reset')
if __name__=='__main__':main()
