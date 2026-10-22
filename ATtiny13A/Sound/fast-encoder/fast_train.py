#!/usr/bin/env python3
"""Fast HQ3 offline encoder: C synthesis, C native STOI + spectral objective,
Python transport/assembly and independently verified quality metrics.

Works on existing MiniLPC HQ3 `.hq` streams, no legacy format in the chip.
The produced stream uses EXACTLY the same AVR decoder and bit layout.
"""
from __future__ import annotations
import argparse,ctypes,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
import numpy as np
import soundfile as sf
from pystoi.utils import _resample_window_oct
from scipy.signal import resample_poly
from pystoi import stoi

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'examples'
VOICE_NAMES=('chego','otvechaesh','vinni','demo')


def unpack_stream(buf: bytes):
    frames=[];dur=[];pos=0;coeff=[0]*4
    while pos<len(buf):
        p=buf[pos];pos+=1
        if p==255:break
        if p&0xc0 == 0xc0:
            length=((p&3)*64) or 256
            if pos>=len(buf):raise ValueError('truncated extended pitch')
            pitch=buf[pos];pos+=1
        else:
            length=((p&0xc0) or 256);pitch=p&63
        if pitch>126:raise ValueError('pitch outside supported range')
        if pos>=len(buf):raise ValueError('truncated header')
        head=buf[pos];pos+=1
        kind=head>>6
        if kind==0:
            if pos+4>len(buf):raise ValueError('truncated full frame')
            coeff=list(buf[pos:pos+4]);pos+=4
        elif kind==2:
            if pos+2>len(buf):raise ValueError('truncated low four coefficients')
            coeff[:2]=buf[pos:pos+2];pos+=2
        elif kind==3:
            if pos+2>len(buf):raise ValueError('truncated high four coefficients')
            coeff[2:]=buf[pos:pos+2];pos+=2
        frames.append([pitch,head&63,*coeff]);dur.append(length)
    if pos!=len(buf):raise ValueError('trailing bytes in stream')
    return np.asarray(frames,dtype=np.uint8),np.asarray(dur,dtype=np.uint16)


def pack_stream(frames: np.ndarray,durations:np.ndarray) -> bytes:
    out=bytearray();prev=[0,0,0,0]
    for i,(row,d) in enumerate(zip(frames,durations)):
        p=int(row[0]);d=int(d)
        if not 0<=p<=126 or d not in (64,128,192,256):raise ValueError('invalid frame pitch/duration')
        if d==192 or p>=64:
            out.extend((0xc0 | ((d//64)&3),p))
        else: out.append((d&0xc0)|p)
        cur=list(map(int,row[2:6]))
        if i==0 or (cur[:2]!=prev[:2] and cur[2:]!=prev[2:]):kind=0
        elif cur==prev:kind=1
        elif cur[:2]!=prev[:2]:kind=2
        else:kind=3
        out.append((int(row[1])&63)|(kind<<6))
        if kind==0:out.extend(cur)
        elif kind==2:out.extend(cur[:2])
        elif kind==3:out.extend(cur[2:])
        prev=cur
    return bytes(out)


class Native:
    def __init__(self,reference:np.ndarray):
        self.lib=ctypes.CDLL(str(HERE/'libmicrolpc.so'))
        L=self.lib
        p8=ctypes.POINTER(ctypes.c_uint8)
        p16=ctypes.POINTER(ctypes.c_uint16)
        pd=ctypes.POINTER(ctypes.c_double)
        pf=ctypes.POINTER(ctypes.c_float)
        L.mlpc_create.argtypes=[pf,ctypes.c_int,pd,ctypes.c_int]
        L.mlpc_create.restype=ctypes.c_void_p
        L.mlpc_destroy.argtypes=[ctypes.c_void_p]
        L.mlpc_decode.argtypes=[p8,p16,ctypes.c_int,p8,ctypes.c_int]
        L.mlpc_decode.restype=ctypes.c_int
        L.mlpc_metrics.argtypes=[ctypes.c_void_p,p8,ctypes.c_int,pd]
        L.mlpc_metrics.restype=ctypes.c_int
        L.mlpc_analyze.argtypes=[pf,ctypes.c_int,ctypes.c_int,p8,p16,ctypes.c_int]
        L.mlpc_analyze.restype=ctypes.c_int
        L.mlpc_stream_bytes.argtypes=[p8,p16,ctypes.c_int]
        L.mlpc_stream_bytes.restype=ctypes.c_int
        L.mlpc_optimize.argtypes=[ctypes.c_void_p,p8,p16,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_double,pd,pd]
        L.mlpc_optimize.restype=ctypes.c_int
        ref=np.ascontiguousarray(reference,dtype=np.float32)
        filt=_resample_window_oct(10000,7500)
        filt=np.ascontiguousarray(filt/np.sum(filt),dtype=np.float64)
        self.ref=ref
        self.ptr=L.mlpc_create(ref.ctypes.data_as(pf),len(ref),filt.ctypes.data_as(pd),len(filt))
        if not self.ptr:raise RuntimeError('Native objective failed to initialize')
    def analyze(self,hop=256):
        frame_capacity=(len(self.ref)+hop-1)//hop
        f=np.zeros((frame_capacity,6),dtype=np.uint8)
        d=np.zeros(frame_capacity,dtype=np.uint16)
        n=self.lib.mlpc_analyze(
            self.ref.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),len(self.ref),hop,
            f.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
            d.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),len(f))
        if n<1:raise RuntimeError(f'Native initial analysis error {n}')
        assert int(d[:n].sum())==len(self.ref)
        return f[:n],d[:n]

    def close(self):
        if self.ptr:self.lib.mlpc_destroy(self.ptr);self.ptr=None
    def decode(self,frames,durations):
        f=np.ascontiguousarray(frames,dtype=np.uint8)
        d=np.ascontiguousarray(durations,dtype=np.uint16)
        dst=np.empty(int(d.sum()),dtype=np.uint8)
        k=self.lib.mlpc_decode(f.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),d.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),len(f),dst.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),len(dst))
        if k!=len(dst):raise RuntimeError(f'Native decoder returned {k}, expected {len(dst)}')
        return dst
    def metrics(self,pcm):
        pcm=np.ascontiguousarray(pcm,np.uint8)
        arr=np.zeros(3,np.float64)
        result=self.lib.mlpc_metrics(self.ptr,pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),len(pcm),arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        if result:raise RuntimeError('Native score failed')
        return arr
    def optimize(self,frames,durations,budget:int,evals:int,seed:int,spec_weight:float=0.015):
        f=np.ascontiguousarray(frames,dtype=np.uint8).copy();d=np.ascontiguousarray(durations,dtype=np.uint16)
        before=np.zeros(3,np.float64);after=np.zeros(3,np.float64)
        accepted=self.lib.mlpc_optimize(self.ptr,f.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),d.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),len(f),budget,evals,seed,spec_weight,before.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),after.ctypes.data_as(ctypes.POINTER(ctypes.c_double)))
        if accepted<0:raise RuntimeError(f'Native optimizer error {accepted}')
        return f,dict(accepted=accepted,before=before.tolist(),after=after.tolist())


def python_metrics(ref,pcm):
    from pystoi import stoi
    import scipy.signal
    x=ref.astype(np.float32)
    y=(pcm.astype(np.float32)-128.)/128.
    return float(stoi(x,y,7500,extended=False))


def make_firmware(source:Path,encoded:bytes,destination:Path):
    """Build a fresh AVR HEX using unchanged C-optimized AVR assembly."""
    destination.mkdir(parents=True,exist_ok=True)
    text=source.read_text()
    (destination/'speech.hq').write_bytes(encoded)
    # Two-stage assembly: locate the code_end symbol, pack without gaps.
    import re
    text=re.sub(r'\.set VOICE_ADDR,0x[0-9a-fA-F]+','.set VOICE_ADDR,0x200',text)
    (destination/'firmware.S').write_text(text)
    def assemble():
        subprocess.run(['clang','-target','avr','-mmcu=attiny13','-c','firmware.S','-o','firmware.o'],cwd=destination,check=True,capture_output=True)
    assemble()
    symbols=subprocess.run(['llvm-objdump','-t','firmware.o'],cwd=destination,check=True,capture_output=True,text=True).stdout
    code=None
    for line in symbols.splitlines():
        parts=line.split()
        if parts and parts[-1]=='code_end':code=int(parts[0],16);break
    if code is None:raise RuntimeError('Missing code_end symbol')
    text=text.replace('.set VOICE_ADDR,0x200',f'.set VOICE_ADDR,0x{code:x}')
    (destination/'firmware.S').write_text(text)
    assemble()
    subprocess.run(['llvm-objcopy','-O','binary','firmware.o','firmware.bin'],cwd=destination,check=True,capture_output=True)
    data=(destination/'firmware.bin').read_bytes()
    if len(data)>1024:raise RuntimeError(f'Flash limit exceeded: {len(data)}')
    if data[code:code+len(encoded)]!=encoded:raise RuntimeError('Speech data bytes not in expected Flash segment')
    out=[]
    for addr in range(0,len(data),16):
        block=data[addr:addr+16];vals=[len(block),(addr>>8)&255,addr&255,0,*block];vals.append(-sum(vals)&255)
        out.append(':'+''.join(f'{v:02X}' for v in vals))
    (destination/'firmware.hex').write_text('\n'.join(out+[':00000001FF'])+'\n')
    return len(data),code,hashlib.sha256(data).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--voice',default='chego',help='Any short clip name, e.g. chego or myclip')
    ap.add_argument('--evals',type=int,default=1000)
    ap.add_argument('--seed',type=int,default=20261021)
    ap.add_argument('--output',type=Path,default=HERE/'outputs')
    ap.add_argument('--from-wav',action='store_true',help='Analyze an entirely new 7500 Hz WAV in native C')
    ap.add_argument('--input-stream',type=Path,default=None,help='Continue learning from a previously optimized .hq')
    ap.add_argument('--reference',type=Path,default=None,help='Override the reference WAV')
    ap.add_argument('--asm-template',type=Path,default=None,help='Alternate AVR decoder assembly source')
    ap.add_argument('--no-build',action='store_true')
    ap.add_argument('--spec-weight',type=float,default=0.015,help='Spectral-error penalty in rate-distortion objective; 0 = prioritize STOI')
    args=ap.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',args.voice):
        raise ValueError('Voice name must contain only ASCII letters, digits, _ or -')
    base=SOURCE/args.voice
    ref,sr=sf.read(args.reference if args.reference else base/'original.wav')
    if sr!=7500:raise ValueError('Input reference must be 7500 Hz')
    if ref.ndim!=1:raise ValueError('Only mono WAV references are supported')
    native=Native(ref)
    try:
        if args.from_wav:
            frames,d=native.analyze(256)
            stream=pack_stream(frames,d)
        else:
            stream=(args.input_stream if args.input_stream else base/'speech.hq').read_bytes()
            frames,d=unpack_stream(stream)
            if pack_stream(frames,d)!=stream:raise ValueError('Codec roundtrip error')
        if int(d.sum())!=len(ref):raise ValueError('Reference and stream duration mismatch')
        pcm0=native.decode(frames,d)
        py0=python_metrics(ref,pcm0)
        nm0=native.metrics(pcm0)
        budget=1024-406-1
        if len(stream)>budget:raise ValueError('Starting stream exceeds flash budget')
        t0=time.perf_counter()
        f2,report=native.optimize(frames,d,budget,args.evals,args.seed,args.spec_weight)
        seconds=time.perf_counter()-t0
        final=pack_stream(f2,d)
        pcm1=native.decode(f2,d)
        py1=python_metrics(ref,pcm1);nm1=native.metrics(pcm1)
        if py1+0.00015 < py0:raise RuntimeError('Verified Python STOI regressed: rejecting candidate')
        if len(final)>budget:raise RuntimeError('Native optimizer exceeded speech budget')
        dest=args.output/args.voice;dest.mkdir(parents=True,exist_ok=True)
        (dest/'speech.hq').write_bytes(final)
        (dest/'expected_pcm.raw').write_bytes(pcm1.tobytes())
        sf.write(dest/'decoded.wav',(pcm1.astype(np.float64)-128)/128,7500,subtype='PCM_16')
        if not args.no_build:
            asm=args.asm_template or (base/'firmware.S' if (base/'firmware.S').exists() else HERE/'decoder_template.S')
            flash,code,sha=make_firmware(asm,final,dest)
        else:flash,code,sha=None,None,None
        manifest=dict(voice=args.voice,original_stream_bytes=len(stream),new_stream_bytes=len(final),frame_count=len(frames),samples=len(pcm1),native_before=nm0.tolist(),native_after=nm1.tolist(),verified_stoi_before=py0,verified_stoi_after=py1,accepted_changes=report['accepted'],evaluations_requested=args.evals,elapsed_seconds=round(seconds,3),flash=flash,code=code,sha256=sha)
        (dest/'result.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
        print(json.dumps(manifest,indent=2,ensure_ascii=False))
    finally:native.close()

if __name__=='__main__':main()
