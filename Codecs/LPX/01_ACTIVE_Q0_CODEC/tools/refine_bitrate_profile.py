"""Refine an existing LPX8/12/16 stream without changing its MCU decoder.

Optional legacy or speech v4/v5 seeds must represent the same complete WAV.
The explicit rollback, byte cap, PCM16 and PWM SSE/STOI floors are retained.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
from budget_search import search_budget
from joint_rate import encode_joint
from refine_speech8 import legacy_seed
from benchmark_profile_development import checked,choose,lambda_grid
from standard_metrics import error_metrics,pwm_duties,pwm_pcm16
from benchmark_standards import sha
from output_paths import protect_outputs

def refine(reference,baseline,decoder,max_bytes,rate=12000,kind='speech',seeds=(),center=None):
    ref=np.asarray(reference)
    if rate not in (8000,12000,16000) or kind not in ('speech','music'):
        raise ValueError('Choose speech/music and an8/12/16kbit family')
    if ref.ndim!=1 or ref.dtype.kind not in 'iu' or not 1<=len(ref)<=64000 or np.any(ref<-32768) or np.any(ref>32767):
        raise ValueError('Expected complete mono PCM16 reference,1..64000 samples')
    if not 20<=max_bytes<=65535 or int(max_bytes)!=max_bytes or len(baseline)>max_bytes:
        raise ValueError('A feasible complete-file rollback is required')
    if len(baseline)<20:raise ValueError('Short rollback header')
    started=time.perf_counter();base=checked(baseline,ref,decoder,kind,'rollback');legacy=[]
    for blob in seeds:
        if len(blob)<20:raise ValueError('Short seed header')
        b=legacy_seed(blob) if len(blob)>4 and blob[4] in (4,5) else blob
        checked(b,ref,decoder,kind,'seed');legacy.append(b)
    candidates=[];search={'trials':0}
    if base[2]['full_sse']:
        _,_,search=search_budget([baseline,*legacy],ref,decoder,int(max_bytes),kind,
            lambdas=lambda_grid(rate,center),refinement_trials=2,encoder=encode_joint,encoder_options={'beam':8},
            candidate_sink=lambda b,p,m:candidates.append((b,p,{**m,'quality':error_metrics(ref,p,kind=='speech')})))
    chosen,gates=choose(candidates,base,ref,kind,int(max_bytes))
    actual=checked(chosen[0],ref,decoder,kind,chosen[2].get('source','selected'))
    def record(p):
        b,pcm,m=p
        return {'stream_sha256':sha(b),'pcm16_sha256':sha(pcm.astype('<i2').tobytes()),'pwm_sha256':sha(pwm_duties(pcm).tobytes()),
            'file_bytes':len(b),'file_bps':len(b)*8*8000/len(ref),'payload_bps':(len(b)-20)*8*8000/len(ref),
            'pcm16':m['quality'],'pwm':error_metrics(ref,pwm_pcm16(pcm),kind=='speech')}
    return actual[0],actual[1],{'samples':len(ref),'sample_rate_hz':8000,'rate_family_bps':rate,
        'max_complete_file_bytes':int(max_bytes),'baseline':record(base),'selected':record(actual),
        'changed':sha(actual[0])!=sha(baseline),'beam':8,'lambdas':list(lambda_grid(rate,center)),
        'search_trials':search['trials'],'selection':gates,'seconds':time.perf_counter()-started,
        'decoder_modified':False,'avr_cycles_measured':False,'native_model_exact':True}

def run(reference,baseline,output,rate=12000,kind='speech',seeds=(),max_bytes=None):
    reference,baseline,output=Path(reference),Path(baseline),Path(output);seeds=list(map(Path,seeds))
    paths=[output/'audio.l4hy',output/'decoded.wav',output/'report.json']
    protect_outputs([reference,baseline,*seeds],paths)
    ref,sr=sf.read(reference,dtype='int16')
    if sr!=8000 or ref.ndim!=1:raise ValueError('Reference must be mono PCM16/8kHz')
    cap=20+rate*len(ref)//64000 if max_bytes is None else max_bytes
    with BatchSession('batch',v3_features=24) as decoder:
        b,p,r=refine(ref,baseline.read_bytes(),decoder,cap,rate,kind,[p.read_bytes() for p in seeds])
    output.mkdir(parents=True,exist_ok=True);paths[0].write_bytes(b);sf.write(paths[1],p,8000,subtype='PCM_16')
    paths[2].write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');return r

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('reference',type=Path);ap.add_argument('baseline',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--audio-kbps',type=int,choices=(8,12,16),default=12);ap.add_argument('--kind',choices=('speech','music'),default='speech')
    ap.add_argument('--seed',type=Path,action='append',default=[]);ap.add_argument('--max-bytes',type=int)
    a=ap.parse_args();r=run(a.reference,a.baseline,a.output,a.audio_kbps*1000,a.kind,a.seed,a.max_bytes)
    print(json.dumps({k:r[k] for k in ('changed','search_trials','seconds')}))
