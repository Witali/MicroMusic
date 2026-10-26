#!/usr/bin/env python3
"""Explicit WAV -> low-rate LPX Q0 encoder; original decoder and CLI retained.

One independently decoded segment, at most eight seconds. --max-bytes counts
the complete file; --audio-kbps budgets payload by exact reference duration.
Joint waveform search is the default here; perceptual tradeoffs are opt-in.
"""
import argparse,json
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from wav_lpc import load_wav
from wav_to_lpx4 import encode_segment
from budget_search import search_budget,spectrum_seeds
from joint_rate import encode_joint
from perceptual_rate import refine_perceptual
from standard_metrics import compare
from output_paths import protect_outputs
from level_policy import DEFAULT_LEVEL_FLOOR_DB, relative_energy_floor


def encode_lowrate(reference,decoder,max_bytes,kind='speech',stage='joint',
                   lambdas=(.001,.003,.01,.03,.1,.3,1.),refinement_trials=2,level_floor_db=DEFAULT_LEVEL_FLOOR_DB):
    ref=np.asarray(reference)
    if stage not in ('target','joint','perceptual') or kind not in ('speech','music'):
        raise ValueError('Unknown explicit encoder profile')
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or np.any(ref < -32768) or np.any(ref>32767):
        raise ValueError('Expected one PCM16 segment of 1..64000 samples')
    if not 20<=max_bytes<=65535 or int(max_bytes)!=max_bytes:raise ValueError('Complete file cap must be an integer in 20..65535 bytes')
    relative_energy_floor(ref,float(level_floor_db))
    pool=[]
    encode_segment(ref.astype(np.int16),decoder,max_bytes=65535,lambdas=(0.,),kind=kind,
                   candidate_sink=lambda b,r:pool.append((b,r)),level_floor_db=level_floor_db)
    legacy=[p for p in pool if p[1]['profile']=='legacy']
    dense=(legacy or sorted(pool,key=lambda p:(p[1]['quality']['rmse'],len(p[0]))))[0][0]
    held,audit=spectrum_seeds(dense,(2,4));seeds=[dense,*held]
    seeds.extend(b for b,r in pool if r['profile']=='flat')
    # Preserve the old public WAV encoder's feasible result, not just the
    # high-quality oversized analysis seeds. This supplies its STOI/SSE floor
    # to target search; no-fit of the old bounded search is not fatal here.
    try:
        legacy_blob,_,legacy_report=encode_segment(ref.astype(np.int16),decoder,max_bytes=int(max_bytes),kind=kind,level_floor_db=level_floor_db)
    except ValueError as error:
        if not str(error).startswith('No candidate fits the byte budget'):raise
        legacy_blob=None;legacy_report=None
    if legacy_blob is not None:seeds.append(legacy_blob)
    blob,pcm,target=search_budget(seeds,ref,decoder,int(max_bytes),kind,lambdas=lambdas,
                                refinement_trials=refinement_trials,encoder_options={'level_floor_db':level_floor_db})
    report={'stage':stage,'max_bytes':int(max_bytes),'samples':len(ref),'sample_rate':8000,
            'spectrum_audit':audit,'target_search':target,'decoder_modified':False,
            'legacy_target_available':legacy_blob is not None,'legacy_target':legacy_report,
            'avr_cycles_measured':False,'status':target['status'],
            'level_floor_db':float(level_floor_db),'level_reference':'whole-recording RMS; soft error floor, no gate'}
    if blob is None:return None,None,report
    if stage in ('joint','perceptual'):
        blob,pcm,joint=search_budget([blob],ref,decoder,int(max_bytes),kind,
            lambdas=(.001,.003,.01,.03,.1),refinement_trials=3,encoder=encode_joint,encoder_options={'beam':4,'level_floor_db':level_floor_db})
        report['joint_search']=joint
    if stage=='perceptual':
        blob,pcm,perceptual=refine_perceptual(blob,ref,decoder,kind=kind)
        report['perceptual_search']=perceptual
    report.update(file_bytes=len(blob),audio_packet_bytes=len(blob)-20,
                  audio_kbps=(len(blob)-20)*8*8000/len(ref)/1000,
                  metrics=compare(ref,pcm,kind=='speech',known_delay=0)[0])
    return blob,pcm,report


def run(source,output,max_bytes=None,audio_kbps=None,kind='speech',stage='joint',level_floor_db=DEFAULT_LEVEL_FLOOR_DB):
    source,output=Path(source),Path(output)
    paths=[output/'audio.l4hy',output/'decoded.wav',output/'manifest.json']
    protect_outputs([source],paths)
    ref,input_report=load_wav(source)
    if len(ref)>64000:raise ValueError('This explicit profile handles one segment of at most 8s; split longer audio into independent segments')
    if (max_bytes is None)==(audio_kbps is None):raise ValueError('Choose exactly one file or audio-packet budget')
    if audio_kbps is not None:
        if not np.isfinite(audio_kbps) or not 0<audio_kbps<=64:raise ValueError('Expected positive audio bitrate up to 64kb/s')
        max_bytes=min(65535,20+int(audio_kbps*1000*len(ref)/8000/8))
    with BatchSession('batch',v3_features=24) as decoder:
        blob,pcm,r=encode_lowrate(ref,decoder,max_bytes,kind,stage,level_floor_db=level_floor_db)
    if blob is None:raise ValueError('No candidate reached the target budget; the original input and outputs were not changed')
    output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(blob)
    sf.write(paths[1],pcm,8000,subtype='PCM_16');r['input']=input_report
    paths[2].write_bytes((json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode())
    return r


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input',type=Path);ap.add_argument('output',type=Path)
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--max-bytes',type=int);g.add_argument('--audio-kbps',type=float)
    ap.add_argument('--kind',choices=('speech','music'),default='speech')
    ap.add_argument('--stage',choices=('target','joint','perceptual'),default='joint')
    ap.add_argument('--level-floor-db',type=float,default=DEFAULT_LEVEL_FLOOR_DB,help='Soft energy floor in dB relative to the complete recording RMS')
    a=ap.parse_args();print(json.dumps(run(a.input,a.output,a.max_bytes,a.audio_kbps,a.kind,a.stage,a.level_floor_db),ensure_ascii=False,indent=2))
