"""Reach an explicit LPX file budget from oversized seeds, on the host only.

The original seed's size and quality are observations, not acceptance floors
when it exceeds the target. Feasible seed candidates remain rollback choices.
No-fit describes this finite search, never a lower bound of the LPX format.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from rate_distortion import encode_rate
from wav_to_lpx4 import quality
from output_paths import protect_outputs

LAMBDAS=(0.,.0003,.001,.003,.01,.03,.1,.3,1.,3.)


def spectrum_seeds(seed,strides=(2,4)):
    """Host-only lower-rate LSF proposals, using the existing repeat-frame tag.

    Average complete LSF vectors over each 40/80-ms group, then hold. Audit
    actual quantized/interpolated Q12 filters, not only the float analysis.
    Excitation in these seed templates is requantized by the budget search.
    """
    from lpx4 import decode
    from rice_v7 import absolute_lsf10
    from wav_lpc import pack_frames
    from q0_model import coefficient_trace,filter_stability
    from rate_distortion import serialize
    if any(s not in (1,2,4,8) for s in strides):raise ValueError('Expected existing-frame strides 1/2/4/8')
    frames,blocks,q=decode(seed);vectors=[];cur=None
    for frame in frames:
        if frame[0]==5:cur=np.asarray(absolute_lsf10(frame[1:]),np.int64)
        elif frame[0]==6:cur=cur+np.asarray([v-256 if v>=128 else v for v in frame[1:]],np.int64)
        elif frame[0]!=0 or cur is None:raise ValueError('Invalid Q0 LSF sequence')
        vectors.append(cur.copy())
    outputs=[];audit=[];seen=set()
    for stride in strides:
        held=[]
        for at in range(0,len(vectors),stride):
            mean=np.floor(np.mean(vectors[at:at+stride],axis=0)+.5).astype(np.int64).tolist()
            held.extend([mean]*min(stride,len(vectors)-at))
        proposed=pack_frames(held);signature=b''.join(proposed)
        if signature in seen:continue
        seen.add(signature);check=filter_stability(coefficient_trace(proposed,len(q)))
        record={'stride':stride,'spectrum_update_ms':stride*20,**check,'accepted':not check['unstable_subframes']}
        audit.append(record)
        if record['accepted']:
            blob,_=serialize(seed,proposed,np.asarray(q,np.int64),
                np.asarray([b['scale'] for b in blocks]),np.asarray([b['bits'] for b in blocks]),24)
            outputs.append(blob)
    return outputs,audit


def search_budget(seeds,reference,decoder,max_bytes,kind='speech',lambdas=LAMBDAS,
                  refinement_trials=4,encoder=encode_rate,encoder_options=None,candidate_sink=None):
    ref=np.asarray(reference)
    if (not 20<=max_bytes<=65535 or int(max_bytes)!=max_bytes or ref.ndim!=1 or
            not 1<=len(ref)<=64000 or ref.dtype.kind not in 'iu' or np.any(ref < -32768) or
            np.any(ref > 32767) or kind not in ('speech','music') or not lambdas or
            any(not np.isfinite(v) or v<0 for v in lambdas) or not 0<=refinement_trials<=16):
        raise ValueError('Expected explicit file cap, PCM16, bounded search and valid lambdas')
    seeds=list(dict.fromkeys(bytes(seed) for seed in seeds))
    if not seeds:raise ValueError('At least one existing-format seed required')
    options={'allow_zero':True,'compact_features':24,**(encoder_options or {})}
    started=time.perf_counter();candidates=[];observations=[];seen=set();trials=0
    def add(blob,pcm,record):
        digest=hashlib.sha256(blob).hexdigest()
        if digest in seen:return
        seen.add(digest);m=record['quality'];err=ref.astype(np.int64)-pcm.astype(np.int64)
        row={**record,'file_bytes':len(blob),'audio_packet_bytes':len(blob)-20,
             'stream_sha256':digest,'full_sse':int(np.dot(err,err)),
             'max_abs_error_pcm16':int(np.max(np.abs(err))),'fits_budget':len(blob)<=max_bytes}
        candidates.append((blob,pcm,row));observations.append(row)
        if candidate_sink:candidate_sink(blob,pcm,dict(row))
    for si,seed in enumerate(seeds):
        if int.from_bytes(seed[8:12],'little')!=len(ref):raise ValueError('Seed/reference sample count mismatch')
        pcm=decoder.decode_one_s16(seed,len(ref))
        if pcm is None:raise ValueError('Native decoder rejected seed')
        add(seed,pcm,{'source':'seed','seed_index':si,'quality':quality(ref,pcm,kind)})
        measured=[];tested=set()
        def trial(lam):
            nonlocal trials
            tested.add(float(lam));trials+=1
            blob,pcm,r=encoder(seed,ref,decoder,lam=float(lam),kind=kind,**options)
            measured.append((float(lam),len(blob)));add(blob,pcm,{**r,'source':'rate-search','seed_index':si})
        for lam in sorted(set(lambdas)):trial(lam)
        for _ in range(refinement_trials):
            # Midpoints near the byte boundary are proposals, not a monotonicity
            # assumption: keep all observations, including nonmonotone results.
            ordered=sorted(measured);brackets=[]
            for (a,sa),(b,sb) in zip(ordered,ordered[1:]):
                if (sa<=max_bytes)!=(sb<=max_bytes):
                    middle=(a+b)/2 if not a else np.sqrt(a*b)
                    if middle not in tested:brackets.append((abs(sa-max_bytes)+abs(sb-max_bytes),float(middle)))
            if not brackets:break
            trial(min(brackets)[1])
    eligible=[p for p in candidates if p[2]['fits_budget']]
    baseline=[p for p in eligible if p[2]['source']=='seed']
    if baseline:
        old=min(baseline,key=lambda p:(p[2]['full_sse'],len(p[0]),p[2]['stream_sha256']))
        floor=old[2]['quality']['stoi']
        eligible=[p for p in eligible if p[2]['full_sse']<=old[2]['full_sse'] and
                  (floor is None or p[2]['quality']['stoi']>=floor-1e-12)]
    else:floor=None
    best=min(eligible,key=lambda p:(p[2]['full_sse'],len(p[0]),p[2]['stream_sha256'])) if eligible else None
    frontier=[];loss=float('inf')
    for _,_,row in sorted(candidates,key=lambda p:(len(p[0]),p[2]['full_sse'])):
        if row['full_sse']<loss:frontier.append({k:row[k] for k in ('file_bytes','full_sse','stream_sha256')});loss=row['full_sse']
    report={'status':'ok' if best else 'no_fit','max_bytes':max_bytes,'cap_audio_bytes':max_bytes-20,
            'input_seed_bytes':[len(s) for s in seeds],'started_above_budget':all(len(s)>max_bytes for s in seeds),
            'trials':trials,'candidates':observations,'frontier':frontier,'feasible_seed_stoi_floor':floor,
            'minimum_observed_bytes':min(len(p[0]) for p in candidates),'selected':best[2] if best else None,
            'seconds':time.perf_counter()-started,'decoder_modified':False,
            'no_fit_scope':'Finite encoder search only; no format lower bound is claimed.'}
    return (best[0],best[1],report) if best else (None,None,report)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('seed',type=Path);ap.add_argument('reference',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--max-bytes',type=int,required=True,help='Complete L4HY file cap, including its 20-byte header')
    ap.add_argument('--kind',choices=('speech','music'),default='speech');a=ap.parse_args()
    protect_outputs([a.seed,a.reference],[a.output,a.output.with_suffix('.wav'),a.output.with_suffix('.json')])
    ref,rate=sf.read(a.reference,dtype='int16')
    if rate!=8000 or ref.ndim!=1:raise ValueError('Reference must be mono PCM16 8kHz')
    with BatchSession('batch',v3_features=24) as decoder:
        blob,pcm,r=search_budget([a.seed.read_bytes()],ref,decoder,a.max_bytes,a.kind)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.with_suffix('.json').write_bytes((json.dumps(r,indent=2,ensure_ascii=False)+'\n').encode())
    if blob is None:raise SystemExit('No candidate reached the file cap; details in JSON')
    a.output.write_bytes(blob);sf.write(a.output.with_suffix('.wav'),pcm,8000,subtype='PCM_16')
