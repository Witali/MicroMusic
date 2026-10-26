#!/usr/bin/env python3
"""Convert original LPX3 v1 to LPC3/AVR playback format L3AV v1.

Data: exactly the source LPX3 excitation codes, except that each 80-sample
block selects raw 2/3/4-bit coding or lossless static Huffman for 3-bit codes.
Coefficients: quantized (signed 8-bit with an adaptive per-frame scale) LPC
endpoints, interpolated in the ATmega328 foreground at eight subframes/frame.
Requires Node to execute ORIGINAL LPX3 LPC2-v2 LSF conversion.
The converted stream is *not* directly compatible with old LPX3 v1 players.
"""
from __future__ import annotations
import argparse, json, math, struct, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
# EXACT static tree shared with the decoder; prefix-free and deliberately small.
HUFF={0:'11000',1:'11001',2:'011',3:'00',4:'10',5:'111',6:'010',7:'1101'}
HEADER=struct.Struct('<4sBBHIHHHH')  # 20 B; magic/ver/flags/rate/samples/pre/bright/frame/block

def decode_source(data:bytes):
 if len(data)<24: raise ValueError('short LPX3 header')
 magic,ver,bits,rate,n,base,block,brightness,nblocks=struct.unpack_from('<4sBBHIIHHI',data)
 if magic!=b'LPX3' or ver!=1 or bits not in (2,3,4) or rate!=8000 or block!=80:
  raise ValueError('Only original LPX3 v1 8kHz, block=80, bits=2..4 are supported')
 if base>len(data)-24 or nblocks!=(n+79)//80:raise ValueError('invalid LPX3 lengths')
 offset=24+base+nblocks
 if offset+(n*bits+7)//8>len(data):raise ValueError('truncated original LPX3 payload')
 q=[];reg=nb=0
 for byte in data[offset:]:
  reg|=byte<<nb;nb+=8
  while nb>=bits and len(q)<n:q.append(reg & ((1<<bits)-1));reg>>=bits;nb-=bits
 assert len(q)==n
 return dict(bits=bits,rate=rate,n=n,brightness=brightness,blocks=nblocks,scales=data[24+base:offset],qs=q)

def pack_bits_lsb(vals,bits):
 acc=used=0;result=bytearray()
 for v in vals:
  acc|=v<<used;used+=bits
  while used>=8:result.append(acc&255);acc>>=8;used-=8
 if used:result.append(acc&255)
 return bytes(result)

def pack_huffman(vals):
 acc=used=0;result=bytearray()
 for v in vals:
  code=HUFF[v]
  for bit in code:
   acc=(acc<<1)|int(bit);used+=1
   if used==8:result.append(acc);used=acc=0
 if used:result.append((acc<<(8-used))&255)
 return bytes(result)

def coeff_pack(frame,previous,bits=8,lsf=False):
 if frame==previous:return b'\x00'
 scale,v=frame
 if previous is not None and scale==previous[0]:
  delta=[a-b for a,b in zip(v,previous[1])]
  if all(-8<=d<=7 for d in delta):
   return bytes([2 if bits==8 else 7])+bytes([((delta[i]&15)|((delta[i+1]&15)<<4)) for i in range(0,10,2)])
  if all(-128<=d<=127 for d in delta):
   return bytes([3 if bits==8 else 6])+bytes([d&255 for d in delta])
 if bits==8:return bytes([1]+([] if lsf else [scale]))+bytes([q&255 for q in v])
 # signed 10-bit two's complement, LSB-first, 10 vectors=100 bits = 13 bytes
 return bytes([5]+([] if lsf else [scale]))+pack_bits_lsb([(q&1023) for q in v],10)

def prepare_frames(coeffs,bits=8,lsf=False):
 out=[]
 for f in coeffs:
  v=[float(x) for x in f]
  if lsf:
   scale=(1<<bits)-1; q=tuple(max(0,min(scale,round(x*scale))) for x in v)
  else:
   m=max(abs(x) for x in v)
   # One scale per frame minimizes spectral coefficient quantization errors.
   scale=max(1,min(120 if bits==8 else 255,int(math.floor((126 if bits==8 else 510)/(m+1e-12)))))
   mx=(1<<(bits-1))-1
   q=tuple(max(-mx,min(mx,round(x*scale))) for x in v)
  out.append((scale,q))
 return out

def transcode(inp:Path,out:Path,save_analysis:Path|None=None,coeff_bits=8,rdo_tolerance=None,representation="lsf"):
 original=inp.read_bytes(); src=decode_source(original)
 with tempfile.TemporaryDirectory() as d:
  analysis=Path(d)/'coeff.json'
  run=subprocess.run(['node',str(ROOT/'tools/analyze_lpx3.js'),str(inp),str(analysis)],capture_output=True,text=True)
  if run.returncode:raise RuntimeError(run.stderr or run.stdout)
  co=json.loads(analysis.read_text())
 if save_analysis:save_analysis.write_text(json.dumps(co))
 meta=co['meta'];lsf=representation=='lsf'
 frames=prepare_frames(co['lsfFrame'] if lsf else co['coeffFrame'],coeff_bits,lsf)
 if meta['samples']!=src['n'] or meta['rate']!=src['rate'] or meta['frameSamples']!=160 or len(frames)!=(src['n']+159)//160:
  raise ValueError('incompatible LPC2 source framing (need H=160, 8 subframes)')
 pre=int(round(max(0,min(1,meta['pre']))*16384))
 bri=int(round(max(0,min(.7,src['brightness']/1000))*16384))
 raw=bytearray(HEADER.pack(b'L3AV',1,(1 if coeff_bits==10 else 0)|(2 if lsf else 0),src['rate'],src['n'],pre,bri,160,80))
 candidates=None
 if rdo_tolerance is not None:
  from rdo import optimize
  candidates=optimize(src,co,frames,coeff_bits,rdo_tolerance,lsf)
 preframe=None;counter={'raw':0,'huff':0,'abs':0,'delta4':0,'delta8':0,'same':0}
 for fi,frame in enumerate(frames):
  encoded=coeff_pack(frame,preframe,coeff_bits,lsf);raw.extend(encoded)
  counter[{0:'same',1:'abs',2:'delta4',3:'delta8',5:'abs',6:'delta8',7:'delta4'}[encoded[0]]]+=1
  preframe=frame
  for b in range(2):
   idx=2*fi+b;start=idx*80;qs=src['qs'][start:min(start+80,src['n'])]
   if not qs:continue
   mode=src['bits']
   scale=src['scales'][idx]
   if candidates is not None:
    mode=candidates[idx]['mode'];scale=candidates[idx]['scale'];qs=candidates[idx]['qs']
   r=pack_bits_lsb(qs,mode)
   if mode==3:
    h=pack_huffman(qs)
    if len(h)<len(r):r=h;mode=0x83;counter['huff']+=1
    else:counter['raw']+=1
   else:counter['raw']+=1
   raw.extend((mode,scale));raw.extend(r)
 out.parent.mkdir(exist_ok=True,parents=True);out.write_bytes(raw)
 stats={'original_lpx3_bytes':len(original),'l3av_bytes':len(raw),'ratio':round(len(raw)/len(original),4),
        'saved_bytes':len(original)-len(raw),'samples':src['n'],'rate':src['rate'],
        'frames':len(frames),'huff_blocks':counter['huff'],'raw_blocks':counter['raw'],
        'coeff_modes':{k:counter[k] for k in ('same','abs','delta4','delta8')},
        'original_excitation_bits':src['bits'],'rdo_tolerance':rdo_tolerance,'bits2_blocks':sum(c['mode']==2 for c in candidates) if candidates else 0,'coeff_bits':coeff_bits,'representation':representation,'mode':'closed_loop_RDO' if candidates is not None else 'preserve_excitation_losslessly','note':'LSF/LPC coefficients quantized; integer implementation is lossy'}
 return stats

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');p.add_argument('--report');p.add_argument('--save-analysis');p.add_argument('--coeff-bits',type=int,choices=[8,10],default=8);p.add_argument('--rdo-tolerance',type=float,default=None,help='0.0-0.04: extra preemphasized RMS budget for 2-bit blocks');p.add_argument('--representation',choices=['lsf','lpc'],default='lsf');args=p.parse_args()
 stat=transcode(Path(args.input),Path(args.output),Path(args.save_analysis) if args.save_analysis else None,args.coeff_bits,args.rdo_tolerance,args.representation)
 if args.report:Path(args.report).write_text(json.dumps(stat,ensure_ascii=False,indent=2))
 print(json.dumps(stat,indent=2))
