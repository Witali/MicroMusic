"""Speech v5: exact bounded-Rice spectral packing, optional extra innovations.

No training/codebook. Plain repack preserves every v4 parameter and sample.
Optional innovations change excitation only; all spectra remain exact.
"""
import argparse, struct
from pathlib import Path
import numpy as np
from lpx4 import BitWriter, BitReader, HEADER
import speech_v4 as v4
from q0_model import coefficient_trace, synthesize, table
from wav_lpc import pack_frames


def putrice(w,value,k,width):
    q=value>>k
    if q>=8:w.put(0,8);w.put(value,width)
    else:w.put(0,q);w.put(1,1);w.put(value&((1<<k)-1),k)


def getrice(r,k,width):
    q=0
    while q<8 and not r.get(1):q+=1
    return r.get(width) if q==8 else (q<<k)|r.get(k)


def put_spectrum(w,vec,old,bits):
    if vec==old:w.put(0,1);return 'repeat'
    gaps=[vec[0]]+[b-a-1 for a,b in zip(vec,vec[1:])]
    options=[]
    for delta in (False,True):
        if delta and old is None:continue
        values=[2*(a-b) if a>=b else -2*(a-b)-1 for a,b in zip(vec,old)] if delta else gaps
        k=(0 if bits==5 else 1) if delta else (1 if bits==5 else 2)
        trial=BitWriter()
        for value in values:putrice(trial,value,k,bits+int(delta))
        options.append((trial.total,delta,values,k))
    _,delta,values,k=min(options,key=lambda x:(x[0],x[1]))
    w.put(1,1);w.put(int(delta),1)
    for value in values:putrice(w,value,k,bits+int(delta))
    return 'delta' if delta else 'gap'


def get_spectrum(r,old,bits):
    if not r.get(1):
        if old is None:raise ValueError('Initial spectrum cannot repeat')
        return old.copy()
    delta=bool(r.get(1))
    if delta and old is None:raise ValueError('Initial spectrum cannot use delta')
    k=(0 if bits==5 else 1) if delta else (1 if bits==5 else 2)
    vec=[]
    for i in range(10):
        z=getrice(r,k,bits+int(delta))
        value=old[i]+(z//2 if not z&1 else -(z//2)-1) if delta else (vec[-1]+1 if vec else 0)+z
        if not 0<=value<(1<<bits) or vec and value<=vec[-1]:raise ValueError('Invalid compact spectrum')
        vec.append(value)
    return vec


def components(blob):
    n,pre,bright,vectors,params,pulses=v4.unpack(blob)
    shift=5 if blob[5]==4 else 4
    spectra=[[v>>shift for v in row] for row in vectors[::2]]
    return n,blob[5],spectra,params,pulses,pre,bright


def pack(n,profile,spectra,params,pulses,pre=13926,bright=0,extras=None,force_extras=False):
    # Reuse all v4 geometry/range validation, without changing that format.
    header=bytearray(v4.pack(n,profile,spectra,params,pulses,pre,bright)[:20])
    chunks=len(spectra)*8
    extras=[(-1,0)]*chunks if extras is None else [tuple(map(int,x)) for x in extras]
    if len(extras)!=chunks or any(not -8<=a<=7 or a and not 0<=p<40 for p,a in extras):
        raise ValueError('Invalid extra innovations')
    enhanced=bool(force_extras or any(a for p,a in extras))
    header[4]=5;header[5]=profile|(128 if enhanced else 0)
    w=BitWriter();old=None;counts={'gap':0,'delta':0,'repeat':0}
    for fi,vec in enumerate(spectra):
        mode=put_spectrum(w,list(vec),old,5 if profile==4 else 6);counts[mode]+=1;old=list(vec)
        for half in range(2):
            scale,lag,gain=map(int,params[fi*2+half]);w.put(scale,5);w.put(lag-18,7);w.put(gain//2,3)
            for si in range(4):
                a,b=pulses[fi*16+half*8+si*2:fi*16+half*8+si*2+2]
                if profile==4:
                    for pos,amp in (a,b):
                        w.put(int(np.flatnonzero(v4.POSITIONS4==pos)[0]),4);w.put(int(amp>0),1)
                else:
                    combo=int(a[0]+20*b[0]);w.put(combo&255,8);w.put(combo>>8,1)
                    w.put(int(a[1])&15,4);w.put(int(b[1])&15,4)
                if enhanced:
                    pos,amp=extras[fi*8+half*4+si];w.put(int(amp!=0),1)
                    if amp:w.put(pos,6);w.put(amp&15,4)
    bitcount=w.total;w.aligned();payload=w.get()
    if len(payload)>65513:raise ValueError('Compact stream exceeds ROM API')
    return bytes(header)+struct.pack('<H',len(payload))+payload,{
        'payload_bits':bitcount,'file_bytes':22+len(payload),'enhanced':enhanced,
        'extra_pulses':sum(a!=0 for p,a in extras),'spectrum_modes':counts}


def repack(blob,extras=None,force_extras=False):
    return pack(*components(blob),extras=extras,force_extras=force_extras)


def unpack(blob):
    if len(blob)<22:raise ValueError('Short compact header')
    magic,version,flags,rate,n,pre,bright,frame,block=struct.unpack(HEADER,blob[:20])
    profile=flags&127
    if (magic,version,rate,frame,block)!=(b'L4HY',5,8000,320,160) or profile not in (4,6):
        raise ValueError('Unsupported compact header')
    if not 1<=n<=64000 or pre>16384 or bright>11469 or len(blob)!=22+int.from_bytes(blob[20:22],'little'):
        raise ValueError('Invalid compact geometry')
    spectra=[];params=[];pulses=[];extras=[];old=None;r=BitReader(blob[22:])
    for fi in range((n+319)//320):
        vec=get_spectrum(r,old,5 if profile==4 else 6);spectra.append(vec);old=vec
        for half in range(2):
            params.append((r.get(5),r.get(7)+18,r.get(3)*2))
            for si in range(4):
                if profile==4:
                    for _ in range(2):pulses.append((int(v4.POSITIONS4[r.get(4)]),8 if r.get(1) else -8))
                else:
                    combo=r.get(8)|(r.get(1)<<8)
                    if combo>=400:raise ValueError('Invalid radix20 position pair')
                    for pos in (combo%20,combo//20):
                        amp=r.get(4);pulses.append((pos,amp if amp<8 else amp-16))
                pos,amp=-1,0
                if flags&128 and r.get(1):
                    pos=r.get(6);amp=r.get(4);amp=amp if amp<8 else amp-16
                    if pos>=40:raise ValueError('Invalid extra pulse position')
                extras.append((pos,amp))
    if r.o!=len(r.data) or r.acc:raise ValueError('Unexpected compact trailing data')
    return n,profile,spectra,params,pulses,pre,bright,extras


def decode_model(blob):
    n,profile,spectra,params,pulses,pre,bright,extras=unpack(blob)
    shift=5 if profile==4 else 4
    vectors=[[(v<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)]
    q=[];scales=[]
    for half,(scale,lag,gain) in enumerate(params):
        scales.extend([scale*8]*2)
        for si in range(8):
            pos,amp=pulses[half*8+si]
            for j in range(20):
                at=len(q);ep,ea=extras[at//40]
                predicted=(gain*(q[-lag] if at>=lag else 0)+8)>>4
                q.append(min(31,max(-32,predicted+(amp if j==pos else 0)+(ea if at%40==ep else 0))))
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n)
    return synthesize(np.asarray(q[:n],np.int64),np.asarray(scales,np.int64),co,table('scale_table.inc'),pre,bright)


def main():
    import json
    from batch_decoder import BatchSession
    from output_paths import protect_outputs
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args();protect_outputs([a.input],[a.output]);old=a.input.read_bytes();new,r=repack(old)
    n=int.from_bytes(old[8:12],'little')
    with BatchSession('batch',speech=True,speech_compact=True) as decoder:
        np.testing.assert_array_equal(decoder.decode_one_s16(old,n),decoder.decode_one_s16(new,n))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(new)
    print(json.dumps({'old_bytes':len(old),**r,'pcm16_exact':True}))


if __name__=='__main__':main()
