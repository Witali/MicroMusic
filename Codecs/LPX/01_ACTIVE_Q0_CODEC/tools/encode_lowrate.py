#!/usr/bin/env python3
"""Explicit WAV -> low-rate LPX Q0 encoder; original decoder and CLI retained.

One independently decoded segment, at most eight seconds. --max-bytes counts
the complete file; --audio-kbps budgets payload by exact reference duration.
Joint waveform search is the default here; perceptual tradeoffs are opt-in.
"""
import argparse,hashlib,json
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
from level_policy import DEFAULT_LEVEL_FLOOR_DB, relative_energy_floor, preserves_activity
from gain_search import search_upshift,rescale_excitation
from q0_model import decode_pcm16


def _encode_core(reference,decoder,max_bytes,kind='speech',stage='joint',
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
    # A coarse scalar search can reach the cap only by erasing excitation.
    # Keep bounded, higher-quality alternatives for the joint pitch/sparse
    # search instead of making that already damaged result its only seed.
    # Preserve both zero-preemphasis and LPC families when they are present.
    nearby={}
    def retain_joint_seed(candidate,_pcm,row):
        if not int(max_bytes)<len(candidate)<=min(65535,2*int(max_bytes)):return
        family=int.from_bytes(candidate[12:14],'little')==0
        rank=(row['full_sse'],len(candidate),row['stream_sha256'])
        if family not in nearby or rank<nearby[family][0]:nearby[family]=(rank,candidate)
    blob,pcm,target=search_budget(seeds,ref,decoder,int(max_bytes),kind,lambdas=lambdas,
                                refinement_trials=refinement_trials,encoder_options={'level_floor_db':level_floor_db},
                                candidate_sink=retain_joint_seed)
    report={'stage':stage,'max_bytes':int(max_bytes),'samples':len(ref),'sample_rate':8000,
            'spectrum_audit':audit,'target_search':target,'decoder_modified':False,
            'legacy_target_available':legacy_blob is not None,'legacy_target':legacy_report,
            'avr_cycles_measured':False,'status':target['status'],
            'level_floor_db':float(level_floor_db),'level_reference':'whole-recording RMS; soft error floor, no gate'}
    if stage in ('joint','perceptual'):
        joint_seeds=([blob] if blob is not None else [])+[r[1] for r in sorted(nearby.values(),key=lambda r:r[0])]
        if not joint_seeds:return None,None,report
        blob,pcm,joint=search_budget(joint_seeds,ref,decoder,int(max_bytes),kind,
            lambdas=(.001,.003,.01,.03,.1,.3,1.),refinement_trials=3,encoder=encode_joint,encoder_options={'beam':4,'level_floor_db':level_floor_db})
        report['joint_search']=joint
        report['joint_seed_sha256']=[hashlib.sha256(seed).hexdigest() for seed in joint_seeds]
        report['status']=joint['status']
    if blob is None:return None,None,report
    if stage=='perceptual':
        blob,pcm,perceptual=refine_perceptual(blob,ref,decoder,kind=kind)
        report['perceptual_search']=perceptual
    report.update(file_bytes=len(blob),audio_packet_bytes=len(blob)-20,
                  audio_kbps=(len(blob)-20)*8*8000/len(ref)/1000,
                  metrics=compare(ref,pcm,kind=='speech',known_delay=0)[0])
    return blob,pcm,report


def encode_lowrate(reference,decoder,max_bytes,kind='speech',stage='joint',
                   lambdas=(.001,.003,.01,.03,.1,.3,1.),refinement_trials=2,level_floor_db=DEFAULT_LEVEL_FLOOR_DB,gain_search=True):
    ref=np.asarray(reference)
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or np.any(ref < -32768) or np.any(ref >32767):
        raise ValueError('Expected one PCM16 segment of 1..64000 samples')
    relative_energy_floor(ref,float(level_floor_db))
    shift=search_upshift(ref) if gain_search else 0
    searched=(ref.astype(np.int64)*(1<<shift)).astype(np.int16)
    blob,pcm,report=_encode_core(searched,decoder,max_bytes,kind,stage,lambdas,refinement_trials,level_floor_db)
    report['search_gain_shift']=shift
    if blob is None:return None,None,report
    if shift:
        report['search_level_metrics']=report.pop('metrics')
        blob=rescale_excitation(blob,shift)
        if len(blob)>max_bytes:
            report['status']='no_fit';report['no_fit_reason']='Rescaled proposal exceeds byte cap'
            return None,None,report
        pcm=decoder.decode_one_s16(blob,len(ref))
        if pcm is None or not np.array_equal(pcm,decode_pcm16(blob)):raise AssertionError('Gain proposal native/model mismatch')
    if stage in ('joint','perceptual'):
        source_energy=float(np.dot(ref.astype(np.float64),ref.astype(np.float64)))
        def guard(candidate):
            error=ref.astype(np.float64)-np.asarray(candidate,dtype=np.float64)
            return preserves_activity(ref,candidate,level_floor_db) and float(np.dot(error,error))<=source_energy
        starting=blob
        if shift:
            try:
                old,_,legacy=encode_segment(ref.astype(np.int16),decoder,max_bytes=int(max_bytes),kind=kind,level_floor_db=level_floor_db)
            except ValueError as error:
                if not str(error).startswith('No candidate fits the byte budget'):raise
                old=None;legacy=None
            report['legacy_target_available']=old is not None;report['legacy_target']=legacy
        else:old=None
        candidates=list(dict.fromkeys([starting]+([old] if old is not None else [])))
        # Scale remapping is only a proposal. Its STOI can remain high despite
        # a large fixed-point DC/level error; do not make that proposal an
        # acceptance floor for correction at the real input level.
        baselines=([candidates.index(old)] if old is not None else []) if shift else None
        for weighting in ('balanced','recording'):
            refined,decoded,details=search_budget(candidates,ref,decoder,int(max_bytes),kind,
                lambdas=(.001,.003,.01,.03,.1,.3,1.),refinement_trials=3,encoder=encode_joint,
                encoder_options={'beam':4,'level_floor_db':level_floor_db,'error_weighting':weighting},candidate_guard=guard,
                baseline_seed_indices=baselines)
            report[weighting+'_search']=details
            if refined is not None:blob,pcm=refined,decoded;candidates=[refined];baselines=None
        if not guard(pcm):
            report['status']='no_fit';report['no_fit_reason']='No candidate passed the sustained-mute and waveform-error checks'
            return None,None,report
        report['activity_guard_db']=float(level_floor_db)
        report['requires_error_no_worse_than_silence']=True
    report.update(status='ok',file_bytes=len(blob),audio_packet_bytes=len(blob)-20,
                  audio_kbps=(len(blob)-20)*8*8000/len(ref)/1000,
                  metrics=compare(ref,pcm,kind=='speech',known_delay=0)[0])
    return blob,pcm,report


def run(source,output,max_bytes=None,audio_kbps=None,kind='speech',stage='joint',level_floor_db=DEFAULT_LEVEL_FLOOR_DB,gain_search=True):
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
        blob,pcm,r=encode_lowrate(ref,decoder,max_bytes,kind,stage,level_floor_db=level_floor_db,gain_search=gain_search)
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
    ap.add_argument('--no-gain-search',action='store_true',help='Disable the internal integer-headroom proposal')
    a=ap.parse_args();print(json.dumps(run(a.input,a.output,a.max_bytes,a.audio_kbps,a.kind,a.stage,a.level_floor_db,not a.no_gain_search),ensure_ascii=False,indent=2))
