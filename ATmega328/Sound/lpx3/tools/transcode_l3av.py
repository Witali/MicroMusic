#!/usr/bin/env python3
"""L3AV 1 -> 2 optional Rice/dynamic offline pair compression.
No audio quality loss; exactly preserves quantized excitation and 10 LPC coefficients.
"""
from pathlib import Path
import sys,argparse,json
from l3av_parse import unpack
from offline_pair_dictionary import rice_candidate,compress,decompress

def rice_only(doc):
    b=bytearray(doc['raw'][:20]);b[4]=2;b[5]&=3
    nraw=nencoded=0
    for j,frame in enumerate(doc['frames']):
        b.extend(frame)
        for k in range(2):
            ix=2*j+k
            if ix>=len(doc['blocks']):break
            bl=doc['blocks'][ix];ric=rice_candidate(bl)
            if ric is None:
                b.extend(bl['bytes']);nraw+=1
            else:
                b.extend(ric);nencoded+=1
    return bytes(b),{'strategy':'rice','rice_blocks':nencoded,'raw_blocks':nraw,'dict_blocks':0,'updates':0,'hits':0}

def transcode(source, dest, strategy='rice', cap=64, window=4):
    doc=unpack(Path(source).read_bytes())
    if strategy=='rice':data,extra=rice_only(doc)
    else:
        data,extra=compress(doc,cap=cap,window=window,tiered=True,fallback=True,rice=(strategy=='hybrid'))
        extra=dict(extra,strategy=strategy)
    frames,blocks=decompress(data)
    if frames!=doc['frames'] or [(x['bits'],x['scale'],x['q']) for x in blocks] != [(x['bits'],x['scale'],x['q']) for x in doc['blocks']]:
        raise RuntimeError('lossless verification failed')
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    stats={'input':str(source),'output':str(dest),'input_bytes':len(doc['raw']),'output_bytes':len(data),
            'saved_bytes':len(doc['raw'])-len(data),'reduction_pct':round(100*(len(doc['raw'])-len(data))/len(doc['raw']),3),
            'sample_count':doc['sampleCount'], 'lossless_excitation':True,'same_lpc_coefficients':True,**extra}
    return stats

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('source');p.add_argument('destination')
    p.add_argument('--strategy',choices=['rice','dictionary','hybrid'],default='rice')
    p.add_argument('--dictionary-bytes',type=int,choices=[64,128,256,512],default=64)
    p.add_argument('--window-blocks',type=int,default=4)
    a=p.parse_args()
    print(json.dumps(transcode(a.source,a.destination,strategy=a.strategy,cap=a.dictionary_bytes,window=a.window_blocks),ensure_ascii=False,indent=2))
