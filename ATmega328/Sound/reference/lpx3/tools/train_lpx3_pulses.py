#!/usr/bin/env python3
"""LPX3 -> tiny, pitch-synchronous excitation codebook feasibility experiment.

This does NOT compile LPX3 to an AVR-compatible stream! Instead, it trains
four 8-tap signed-4-bit pulse patterns from the (true) LPX3 residual, and packs
one 2-bit pattern selector per 256-sample LPC frame. Exports a 64-byte EEPROM
image with a 16-byte codebook, selector stream, and measured residual-pulse fit.
CPU target integration and subjective speech-quality validation are future work.
"""
from __future__ import annotations
import argparse, json, math, struct, pathlib
import numpy as np
from scipy.signal import resample_poly
from sklearn.cluster import KMeans

HEADER=struct.Struct('<4sBBHIIHHI')
FRAME=256
TAPS=8
K=4

def get_lpx3_residual(path):
    d=path.read_bytes()
    if len(d)<HEADER.size:raise ValueError('Short LPX3 file')
    magic,version,bits,sr,n,baselen,bs,reserved,nblocks=HEADER.unpack_from(d)
    if magic!=b'LPX3' or version!=1 or bits not in (2,3,4):raise ValueError('Unsupported LPX3')
    pos=HEADER.size+baselen
    scales=d[pos:pos+nblocks]
    b=d[pos+nblocks:]
    if nblocks!=(n+bs-1)//bs or len(b)<math.ceil(n*bits/8):raise ValueError('Truncated LPX3')
    accum=0;left=0;values=[];it=iter(b)
    for i in range(n):
        while left<bits:
            accum |= next(it)<<left;left+=8
        code=accum&((1<<bits)-1);accum >>= bits;left-=bits
        signed=code-(1<<(bits-1))
        sc=0.001*2**((scales[i//bs]-128)/16)
        values.append(signed*sc)
    res=resample_poly(np.asarray(values,dtype=np.float64),15,16)
    return res,{'original_bytes':len(d),'sample_rate':sr,'samples':n,'bits_per_sample':bits}

def snippets_by_frame(res,frames):
    ret=[];labels=[]
    for i in range(frames):
        x=res[256*i:256*(i+1)]
        if len(x)<256:break
        energy=np.sqrt(np.mean(x*x))
        if energy<0.0004:continue
        # Local largest excitation peaks as candidates for glottal pulse shapes.
        peaks=np.argsort(-np.abs(x))[::1]
        selected=[]
        for pi in peaks:
            if pi<2 or pi+6>255 or any(abs(pi-s)<11 for s in selected):continue
            selected.append(pi)
            if len(selected)==5:break
        for pi in selected:
            a=x[pi-2:pi+6]
            maximum=np.max(np.abs(a))
            if maximum<0.0005:continue
            a=a/max(maximum,1e-8)
            if a[2]<0:a=-a
            ret.append(a)
            labels.append(i)
    if len(ret)<K*4:raise ValueError('Not enough speech pulses')
    return np.asarray(ret), np.asarray(labels,dtype=np.int32)

def quantize(centers):
    # Each 4-bit signed nibble is -8..7; decoded as level/7.0.
    return np.clip(np.round(centers*7.0),-8,7).astype('int8')

def pack_nibbles(arr):
    a=np.asarray(arr).flatten(); assert len(a)%2==0
    return bytes(((int(a[i])&15)|((int(a[i+1])&15)<<4)) for i in range(0,len(a),2))

def train(source: pathlib.Path, dest: pathlib.Path, frames: int,seed=17):
    y,meta=get_lpx3_residual(source)
    X,fi=snippets_by_frame(y,frames)
    rng=np.random.default_rng(seed)
    ids=rng.permutation(len(X))
    train_id=ids[:max(16,int(len(ids)*0.8))]
    test_id=ids[max(16,int(len(ids)*0.8)):]
    km=KMeans(n_clusters=K,n_init=15,random_state=seed).fit(X[train_id])
    Q=quantize(km.cluster_centers_)
    patterns=Q.astype(np.float64)/7.0
    baseline=np.array([2,3,2,-1,0,0,0,0],dtype=float)/3
    # For a fair shape-only comparison, allow a scalar per pulse for both models.
    def sse(a,b):
        power=max(1e-8,float(np.dot(b,b)))
        coeff=max(0,float(np.dot(a,b))/power)
        return float(np.sum((a-coeff*b)**2))
    all_idx=[]
    for a in X:
        all_idx.append(int(np.argmin([sse(a,b) for b in patterns])))
    all_idx=np.asarray(all_idx,dtype=np.int32)
    # Real AVR would receive only ONE index per 256-sample frame. Vote among pulses.
    selectors=np.zeros(frames,dtype=np.uint8)
    for i in range(frames):
        inds=all_idx[fi==i]
        if len(inds):selectors[i]=np.bincount(inds,minlength=K).argmax()
    # Holdout errors under frame-level selector (not best possible per pulse).
    error_ref=np.mean([sse(X[j],baseline) for j in test_id])
    error_profile=np.mean([sse(X[j],patterns[selectors[fi[j]]]) for j in test_id])
    scores={'reference_mse':round(float(error_ref),6),'profile_mse':round(float(error_profile),6),'relative_change_percent':round(100*(error_profile/error_ref-1),2)}
    # Pack 2bit selectors, little endian 4 per byte.
    packed=bytearray()
    for i in range(0,frames,4):
        b=0
        for j in range(4):
            if i+j<frames:b|=int(selectors[i+j])<<(j*2)
        packed.append(b)
    profiles=pack_nibbles(Q)
    assert len(profiles)==16
    eep=profiles+bytes([255]*(64-len(profiles)))
    dest.mkdir(parents=True,exist_ok=True)
    (dest/'excitation_profiles.eep').write_bytes(eep)
    (dest/'excitation_profiles_16B.bin').write_bytes(profiles)
    (dest/'frame_selectors_2bit.bin').write_bytes(packed)
    result={'source':source.name,'LPX3_bytes':meta['original_bytes'],'AVR_frame_count':frames,'pulse_vectors':len(X),'codebook_bytes':len(profiles),'EEPROM_image_bytes':len(eep),'selector_bytes':len(packed),'frame_selector_bits':2,'patterns_signed4bit':Q.tolist(),'heldout_shape_fit':scores,'important_limit':'Shape-only fit on LPX3 excitation peaks, not STOI or output audio; no AVR implementation.'}
    (dest/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True,type=pathlib.Path)
    parser.add_argument('--frames',type=int,required=True)
    parser.add_argument('--out',required=True,type=pathlib.Path)
    args=parser.parse_args()
    print(json.dumps(train(args.input,args.out,args.frames),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
