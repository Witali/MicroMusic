"""Paired warm encoder timing with byte/state equality, without output caches.

The baseline Python source must be explicitly supplied and hash-pinned.
References and generated media stay local; the summary contains hashes only.
"""
import argparse,hashlib,importlib.util,json,os,platform,statistics,sys,time
from pathlib import Path
import numpy as np
import soundfile as sf
import numba
from batch_decoder import BatchSession
from output_paths import protect_outputs
from standard_metrics import pwm_duties
import joint_rate

def sha(data):return hashlib.sha256(data).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def baseline(path,expected):
    path=Path(path)
    if sha(path.read_bytes())!=expected:raise ValueError('Baseline source hash changed')
    model_path=path.with_name('q0_model_reference.py')
    golden=load(Path(__file__).resolve().parents[1]/'tests/coefficient_trace_golden.json')
    if sha(model_path.read_bytes())!=golden['baseline_source_sha256']:raise ValueError('Baseline coefficient model changed')
    model_spec=importlib.util.spec_from_file_location('q0_model_reference',model_path)
    model=importlib.util.module_from_spec(model_spec);sys.modules[model_spec.name]=model;model_spec.loader.exec_module(model)
    model.ROOT=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('joint_rate_reference',path)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    module.coefficient_trace=model.coefficient_trace
    module.decode_pcm16=model.decode_pcm16
    return module

def clock(call):
    started=time.perf_counter();result=call();return time.perf_counter()-started,result

def run(baseline_source,baseline_sha256,inputs,output,repeats=5,micro_loops=20):
    if not 3<=repeats<=9 or not 1<=micro_loops<=100:raise ValueError('Use3..9 paired repeats and1..100 micro loops')
    cases=load(inputs)['cases']
    if not cases or len({c['id'] for c in cases})!=len(cases):raise ValueError('Missing or duplicate benchmark cases')
    protect_outputs([baseline_source,inputs,*[Path(c[k]) for c in cases for k in ('reference','seed')]],[output])
    old=baseline(baseline_source,baseline_sha256)
    # Reuse deterministic synthetic inputs; expected values were frozen before edits.
    tests=Path(__file__).resolve().parents[1]/'tests';sys.path.insert(0,str(tests))
    from test_joint_trellis_exact import inputs as trellis_inputs,output_hash
    tasks=list(trellis_inputs());golden=load(tests/'joint_trellis_golden.json')
    warm={};digests={}
    for name,module in (('before',old),('after',joint_rate)):
        duration,results=clock(lambda:{key:output_hash(module.trellis(*args)) for key,args in tasks})
        if results!=golden['output_sha256']:raise AssertionError('Trellis state/output changed: '+name)
        warm[name]=duration;digests[name]=sha(json.dumps(results,sort_keys=True).encode())
    times={'before':[],'after':[]}
    def micro(module):
        for _ in range(micro_loops):
            for _,args in tasks:module.trellis(*args)
    for repeat in range(repeats):
        for name,module in ((('before',old),('after',joint_rate)) if repeat%2==0 else (('after',joint_rate),('before',old))):
            elapsed,_=clock(lambda:micro(module));times[name].append(elapsed)
    result={'schema':1,'timing_protocol':'Alternating paired repeats in one process, all output caches bypassed; JIT warmup measured separately.',
        'baseline_source_sha256':baseline_sha256,'current_source_sha256':sha(Path(joint_rate.__file__).read_bytes()),
        'baseline_model_source_sha256':sha(Path(baseline_source).with_name('q0_model_reference.py').read_bytes()),
        'current_model_source_sha256':sha(Path(__file__).with_name('q0_model.py').read_bytes()),
        'python':platform.python_version(),'numpy':np.__version__,'numba':numba.__version__,
        'threads':{k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMBA_NUM_THREADS')},
        'repeats':repeats,'trellis_cases':len(tasks),'micro_loops':micro_loops,'trellis_jit_or_warmup_seconds':warm,
        'trellis_hashes':digests,'trellis_seconds':times,'cases':[],'decoder_modified':False}
    result['trellis_time_reduction_percent']=100*(1-statistics.median(times['after'])/statistics.median(times['before']))
    with BatchSession('batch',v3_features=24) as decoder:
        for c in cases:
            ref,rate=sf.read(c['reference'],dtype='int16');seed=Path(c['seed']).read_bytes()
            if rate!=8000 or ref.ndim!=1 or not 1<=len(ref)<=64000:raise ValueError('Expected complete mono PCM16/8kHz reference')
            if sha(ref.astype('<i2').tobytes())!=c['reference_sha256'] or sha(seed)!=c['seed_sha256']:raise ValueError('Benchmark input changed')
            measured={'before':[],'after':[]};warm={};expected=None
            options={'beam':c.get('beam',4),'lam':c['lambda'],'kind':c['kind']}
            def encode(module):
                b,p,r=module.encode_joint(seed,ref,decoder,**options)
                return b,p,r
            for name,module in (('before',old),('after',joint_rate)):
                elapsed,(blob,pcm,meta)=clock(lambda:encode(module));warm[name]=elapsed
                signature=(sha(blob),sha(pcm.astype('<i2').tobytes()),sha(pwm_duties(pcm).tobytes()))
                if expected is None:expected=signature
                if signature!=expected:raise AssertionError('Full encoder changed stream/PCM/PWM')
            for repeat in range(repeats):
                for name,module in ((('before',old),('after',joint_rate)) if repeat%2==0 else (('after',joint_rate),('before',old))):
                    elapsed,(blob,pcm,meta)=clock(lambda:encode(module));measured[name].append(elapsed)
                    if (sha(blob),sha(pcm.astype('<i2').tobytes()),sha(pwm_duties(pcm).tobytes()))!=expected:
                        raise AssertionError('Non-deterministic full encoder output')
            row={'id':c['id'],'kind':c['kind'],'seed_nominal_bps':c['nominal_bps'],'samples':len(ref),
                'reference_sha256':c['reference_sha256'],'seed_sha256':c['seed_sha256'],'options':options,
                'output_sha256':expected[0],'pcm16_sha256':expected[1],'pwm_sha256':expected[2],
                'file_bytes':len(blob),'output_file_bps':len(blob)*8*8000/len(ref),
                'native_model_exact':meta['native_model_pcm_exact'],
                'warmup_seconds':warm,'seconds':measured,
                'time_reduction_percent':100*(1-statistics.median(measured['after'])/statistics.median(measured['before']))}
            result['cases'].append(row)
            print(row['id'],round(row['time_reduction_percent'],2),'percent less warm encode time; stream/PCM/PWM exact.',flush=True)
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('baseline_source',type=Path);ap.add_argument('baseline_sha256');ap.add_argument('inputs',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--repeats',type=int,default=5);ap.add_argument('--micro-loops',type=int,default=20)
    a=ap.parse_args();run(a.baseline_source,a.baseline_sha256,a.inputs,a.output,a.repeats,a.micro_loops)
