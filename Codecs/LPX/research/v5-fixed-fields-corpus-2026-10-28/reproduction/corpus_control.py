"""Frozen fixed-fields v5 corpus control; all admission uses complete reset chains.

Run from the repository root. Private manifests/media/artifact bindings remain
under the supplied ignored build output. No settings are fitted to any split.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path.cwd();TOOLS=ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'
sys.path.insert(0,str(TOOLS))
import numpy as np
import soundfile as sf
import speech_compact as compact
from speech_rate_allocation import bit_accounting,fit_capacity,improve_extras
from speech_chain_frontier import assemble
from enhance_speech_compact import advance
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames
from refine_speech_compact import quality,no_regression
from standard_metrics import pwm_duties
from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes,validation_sources
from measure_speech_firmware import checked_output
from output_paths import protect_outputs

SETTINGS={'max_render_evaluations':128,'candidate_batch':32,'segment_active_percent_grid':[0,25,50,75,100],
    'segment_byte_percent_grid':[90,95,100],'chain_percent_grid':[100,95,90],
    'chain_beam_width':32,'chain_max_evaluations':4096,'objective':'original-level complete PCM16 SSE',
    'rate_lambda':0,'swap_gate':'complete-chain amplitude-control PCM/PWM SSE and available STOI floors',
    'fields':'spectra/params/base pulses/pre/bright/sample geometry frozen',
    'cap_grid_scope':'finite proposal caps only; total bytes and complete-chain metrics decide admission'}
sha=lambda data:hashlib.sha256(data).hexdigest()
canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def guard_target(path):
    path=Path(path);checked_output(path)
    if path.is_symlink() or path.exists() and path.stat().st_nlink>1:
        raise ValueError('Generated output cannot be a symlink or hardlink')
    return path
def save(path,value):
    path=guard_target(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=guard_target(path.with_suffix(path.suffix+'.writing'))
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n');temporary.replace(path)


def source_binding():
    return {'decoder_sources':source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'),
        'host_sources':validation_sources((Path(__file__),)),
        'python':sys.version,'packages':{name:importlib.metadata.version(name) for name in ('numpy','numba','scipy','pystoi','soundfile')},
        'settings':SETTINGS}


def cap_grid(seeds,fields,total_caps):
    minimum=[]
    for values in fields:
        empty=np.full((len(values[2])*8,2),(-1,0),np.int64)
        minimum.append(len(compact.pack(*values[:7],extras=empty)[0]))
    result=[]
    for i,(seed,values) in enumerate(zip(seeds,fields)):
        extras=np.asarray(values[7],np.int64);active=np.flatnonzero(extras[:,1]);requested={len(seed),minimum[i]}
        for percent in SETTINGS['segment_byte_percent_grid']:requested.add(len(seed)*percent//100)
        for percent in SETTINGS['segment_active_percent_grid']:
            proposal=np.full(extras.shape,(-1,0),np.int64)
            chosen=active[:len(active)*percent//100];proposal[chosen]=extras[chosen]
            requested.add(bit_accounting(values[2],values[1],proposal)['file_bytes'])
        for cap in total_caps:
            requested.add(cap-(sum(map(len,seeds))-len(seed)))
            requested.add(cap-(sum(minimum)-minimum[i]))
        result.append({'caps':sorted(cap for cap in requested if 22<=cap<=len(seed)),
            'out_of_api_proposals':sorted(cap for cap in requested if cap<22),
            'redundant_above_seed_proposals':sorted(cap for cap in requested if cap>len(seed)),
            'minimum_fixed_bytes':minimum[i]})
    return result


def check_binding(expected,manifest_path,manifest_sha):
    if sha(Path(manifest_path).read_bytes())!=manifest_sha or source_binding()!=expected:
        raise ValueError('Frozen manifest/source/runtime/settings changed during corpus control')


def worker(manifest_path,output,index):
    output=checked_output(output);provenance=load(output/'provenance-private.json')
    expected=provenance['binding'];manifest_sha=provenance['manifest_sha256']
    check_binding(expected,manifest_path,manifest_sha)
    manifest=load(manifest_path);row=manifest['records'][index];record_id=f'fixed-{index+1:03d}'
    folder=checked_output(output/record_id);folder.mkdir(parents=True,exist_ok=True)
    result_path=guard_target(folder/'results-private.json');identity=sha(canonical({'manifest':manifest_sha,'record_index':index,'binding':expected,
        'native_libraries':provenance['native_libraries']}))
    libraries=provenance['native_libraries']
    for item in libraries.values():
        if sha(Path(item['path']).read_bytes())!=item['sha256']:raise ValueError('Native decoder library changed')
    if result_path.exists():
        cached=load(result_path);unsigned={k:v for k,v in cached.items() if k!='receipt_sha256'}
        if (cached.get('status')=='complete' and cached.get('identity')==identity
                and cached.get('receipt_sha256')==sha(canonical(unsigned))
                and all(Path(a['path']).resolve().is_relative_to(folder) and Path(a['path']).is_file() and not Path(a['path']).is_symlink()
                        and Path(a['path']).stat().st_nlink==1 and sha(Path(a['path']).read_bytes())==a['sha256']
                        for a in cached.get('artifacts',[]))):
            return {'id':record_id,'cached':True}
    started=time.perf_counter();started_cpu=time.process_time()
    refpath=Path(row['reference']['path']);refraw=refpath.read_bytes()
    if sha(refraw)!=row['reference']['file_sha256']:raise ValueError('Reference file changed')
    reference,rate=sf.read(refpath,dtype='int16')
    if rate!=8000 or reference.ndim!=1 or len(reference)!=row['samples'] or sha(reference.astype('<i2').tobytes())!=row['reference']['pcm16_sha256']:
        raise ValueError('Whole original reference changed')
    seeds=[];fields=[];at=0
    for ordinal,segment in enumerate(row['segments']):
        blob=Path(segment['path']).read_bytes();values=compact.unpack(blob)
        if (sha(blob)!=segment['stream_sha256'] or len(blob)!=segment['file_bytes'] or values[0]!=segment['samples']
                or values[1]!=row['profile'] or segment['start']!=at or segment['index']!=ordinal):
            raise ValueError('Ordered reset segment binding changed')
        seeds.append(blob);fields.append(values);at+=values[0]
    if at!=len(reference) or sum(map(len,seeds))!=row['baseline_bytes']:raise ValueError('Chain baseline geometry changed')
    caps=[b['max_complete_stream_bytes'] for b in row['budgets']]
    for budget in row['budgets']:
        if budget['max_complete_stream_bytes']!=row['baseline_bytes']*budget['percent']//100:raise ValueError('Non-integer total cap')
    grid=cap_grid(seeds,fields,caps)
    targets=[result_path]
    for i,item in enumerate(grid):
        targets.extend(folder/'segments'/f'segment-{i:02d}'/f'cap-{cap}-{policy}.l4hy' for cap in item['caps'] for policy in ('amplitude','swapped'))
    targets.extend(folder/'chains'/f'{percent}-{role}-segment-{i:02d}.l4hy' for percent in SETTINGS['chain_percent_grid']
        for role in ('amplitude','amplitude-original-selected','swapped-accepted','swapped-raw','observed-original-selected') for i in range(len(seeds)))
    protect_outputs([Path(manifest_path),Path(__file__),refpath,*[Path(s['path']) for s in row['segments']]],targets)
    artifacts=[];validated={};generation=[];amplitude_pools=[[] for _ in seeds];swapped_pools=[[] for _ in seeds]
    with BatchSession('batch',prebuilt=Path(libraries['common']['path'])) as common, BatchSession('batch',prebuilt=Path(libraries['v5']['path'])) as v5:
        def validate(blob):
            digest=sha(blob)
            if digest not in validated:
                n=compact.unpack(blob)[0];pcm=compact.decode_model(blob)
                for decoder in (common,v5):
                    native=decoder.decode_one_s16(blob,n);pwm=decoder.decode_one(blob,n)
                    if native is None or pwm is None or not np.array_equal(native,pcm) or not np.array_equal(pwm,pwm_duties(pcm)):
                        raise AssertionError('Current native common/v5/full model PCM/PWM mismatch')
                validated[digest]=pcm.copy()
            return validated[digest]
        baseline_parts=[validate(blob) for blob in seeds];baseline_pcm=np.concatenate(baseline_parts)
        if (sha(baseline_pcm.astype('<i2').tobytes())!=row['baseline_pcm16_sha256']
                or sha(pwm_duties(baseline_pcm).tobytes())!=row['baseline_pwm_sha256']):raise ValueError('Original incumbent PCM/PWM changed')
        baseline_metrics=quality(reference,baseline_pcm);ref64=reference.astype(np.int64)
        for domain in ('pcm16','pwm8'):
            if baseline_metrics[domain]['error_energy']!=row['baseline_metrics'][domain]['error_energy']:
                raise ValueError('Original metric energy binding changed')
            before=row['baseline_metrics'][domain]['stoi'];now=baseline_metrics[domain]['stoi']
            if (before is None)!=(now is None) or before is not None and abs(before-now)>1e-12:
                raise ValueError('Original metric STOI binding changed')
        def join_segment(i,pcm):return np.concatenate([*baseline_parts[:i],pcm,*baseline_parts[i+1:]])
        def retain(path,blob):
            guard_target(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(blob)
            artifacts.append({'path':str(path),'sha256':sha(blob)});return str(path)
        for i,(seed,values,item) in enumerate(zip(seeds,fields,grid)):
            n,profile,sp,params,pulses,pre,bright,extras=values;extras=np.asarray(extras,np.int64)
            start=row['segments'][i]['start'];target=ref64[start:start+n]
            baseline_local=int(np.sum((baseline_parts[i].astype(np.int64)-target)**2))
            other_sse=int(baseline_metrics['pcm16']['error_energy'])-baseline_local
            shift=5 if profile==4 else 4
            vectors=[[(int(v)<<shift)+(1<<(shift-1)) for v in vector] for vector in sp for _ in range(2)]
            co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n);steps=table('scale_table.inc')
            pp=np.asarray(params,np.int64);ii=np.asarray(pulses,np.int64);layout=bit_accounting(sp,profile,extras)
            def render(ee):return advance(co,pp,ii,ee,steps,pre,bright,0,n,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))[0]
            def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
            def objective(pcm):return other_sse+int(np.sum((target-pcm.astype(np.int64))**2))
            search_cache={};gate_cache={}
            for cap in item['caps']:
                control,_,size,removed=fit_capacity(layout['spectrum_bits'],len(sp),profile,extras,cap,0,n)
                control_stream=serialize(control);control_pcm=validate(control_stream)
                if size!=len(control_stream):raise AssertionError('Amplitude accounting differs from serialization')
                control_metrics=quality(reference,join_segment(i,control_pcm));key=(sha(control_stream),size<=cap)
                predicate_calls=[0]
                def admissible(pcm):
                    digest=sha(np.asarray(pcm,dtype='<i2').tobytes());gate_key=(key,digest)
                    if gate_key not in gate_cache:
                        gate_cache[gate_key]=no_regression(quality(reference,join_segment(i,pcm)),control_metrics)
                    predicate_calls[0]+=1;return gate_cache[gate_key]
                begin=time.perf_counter();cpu=time.process_time();reused=key in search_cache
                if reused:result=search_cache[key]
                else:
                    result=improve_extras(sp,profile,extras,cap,stop=n,render=render,objective=objective,serialize=serialize,
                        max_evaluations=SETTINGS['max_render_evaluations'],candidate_batch=SETTINGS['candidate_batch'],admissible=admissible)
                    search_cache[key]=result
                if result.feasible!=(size<=cap) or result.file_bytes!=size:raise AssertionError('Bounded stage lost its fitting amplitude seed')
                swapped_pcm=validate(result.stream)
                if compact.unpack(result.stream)[:7]!=values[:7]:raise AssertionError('Optional stage changed fixed fields')
                swapped_metrics=quality(reference,join_segment(i,swapped_pcm))
                if not no_regression(swapped_metrics,control_metrics):raise AssertionError('Per-segment complete-chain amplitude floors regressed')
                segment_folder=folder/'segments'/f'segment-{i:02d}'
                amp_path=retain(segment_folder/f'cap-{cap}-amplitude.l4hy',control_stream)
                swap_path=retain(segment_folder/f'cap-{cap}-swapped.l4hy',result.stream)
                amplitude_pools[i].append(control_stream);swapped_pools[i].extend((control_stream,result.stream,seed))
                generation.append({'segment':i,'samples':n,'proposal_cap':cap,'amplitude_bytes':size,'proposal_fit':size<=cap,
                    'status':result.status,'removed_extras':removed,'accepted_swaps':result.accepted_swaps,
                    'render_evaluations':0 if reused else result.evaluations,'quality_predicate_calls':predicate_calls[0],
                    'reused_identical_amplitude_seed':reused,'seed_admissible':result.seed_admissible,'quality_admissible':result.quality_admissible,
                    'amplitude_metrics_in_original_context':control_metrics,'swapped_metrics_in_original_context':swapped_metrics,
                    'seconds':time.perf_counter()-begin,'python_process_cpu_seconds':time.process_time()-cpu,
                    'amplitude_path':amp_path,'swapped_path':swap_path,'trace':result.trace})
        chains=[]
        def describe(candidate,percent,role,cap):
            if candidate is None:return None
            if sum(map(len,candidate.streams))!=candidate.file_bytes or candidate.file_bytes>cap:raise AssertionError('True complete chain cap failed')
            actual=np.concatenate([validate(blob) for blob in candidate.streams])
            if not np.array_equal(actual,candidate.pcm):raise AssertionError('Native reset chain differs from assembled full model')
            measured=quality(reference,actual)
            if measured!=candidate.metrics:raise AssertionError('Whole-chain metrics changed after independent reconstruction')
            paths=[retain(folder/'chains'/f'{percent}-{role}-segment-{i:02d}.l4hy',blob) for i,blob in enumerate(candidate.streams)]
            return {'file_bytes':candidate.file_bytes,'objective':candidate.objective,'metrics':measured,
                'original_incumbent_four_floors_passed':no_regression(measured,baseline_metrics),
                'actual_complete_byte_cap_passed':True,'native_common_v5_model_pcm_pwm_exact':True,'paths':paths,
                'automatic_adoption':False}
        for budget in row['budgets']:
            percent=budget['percent'];cap=budget['max_complete_stream_bytes'];begin=time.perf_counter()
            amplitude=assemble(reference,seeds,amplitude_pools,cap,beam_width=SETTINGS['chain_beam_width'],max_evaluations=SETTINGS['chain_max_evaluations'])
            amp_control=amplitude.tradeoff
            swapped=None
            if amp_control is not None:
                swapped=assemble(reference,amp_control.streams,swapped_pools,cap,beam_width=SETTINGS['chain_beam_width'],max_evaluations=SETTINGS['chain_max_evaluations'])
                if swapped.selected is None:raise AssertionError('Whole-chain fitting amplitude rollback was lost')
            amp=describe(amp_control,percent,'amplitude',cap)
            amp_original=describe(amplitude.selected,percent,'amplitude-original-selected',cap)
            accepted=describe(None if swapped is None else swapped.selected,percent,'swapped-accepted',cap)
            raw=describe(None if swapped is None else swapped.tradeoff,percent,'swapped-raw',cap)
            observed=[p for p in [amplitude.selected,amplitude.tradeoff,*amplitude.frontier,
                *([] if swapped is None else [swapped.selected,swapped.tradeoff,*swapped.frontier])] if p is not None and no_regression(p.metrics,baseline_metrics)]
            original_selected=min(observed,key=lambda p:(p.objective,p.file_bytes)) if observed else None
            original=describe(original_selected,percent,'observed-original-selected',cap)
            if accepted is not None and not no_regression(accepted['metrics'],amp['metrics']):raise AssertionError('Final complete-chain amplitude floors regressed')
            chains.append({'percent':percent,'max_complete_stream_bytes':cap,'original_incumbent_bytes':row['baseline_bytes'],
                'original_incumbent_metrics':baseline_metrics,'amplitude':amp,'amplitude_original_selected':amp_original,
                'swapped_accepted':accepted,'swapped_raw':raw,'observed_original_selected':original,
                'amplitude_selection':amplitude.report,'swapped_selection':None if swapped is None else swapped.report,
                'whole_original_chain_rescored':True,'seconds':time.perf_counter()-begin,
                'no_fit_scope':'Finite proposal pools; proportional segment caps never decide final admission.',
                'original_selection_scope':'Returned objective shortlist/frontier candidates only; complete original floors checked separately from amplitude floors.'})
        unique_validated=len(validated)
    check_binding(expected,manifest_path,manifest_sha)
    for item in libraries.values():
        if sha(Path(item['path']).read_bytes())!=item['sha256']:raise ValueError('Native decoder changed during record')
    result={'schema':'lpx-v5-fixed-fields-record-private-v1','status':'complete','identity':identity,'record_index':index,
        'id':record_id,'private_case_id':row['private_case_id'],'profile':row['profile'],'split':row['split'],'cohort':row['cohort'],
        'samples':row['samples'],'segments':len(seeds),'baseline_bytes':row['baseline_bytes'],'grid':grid,'generation':generation,
        'chains':chains,'unique_native_common_v5_model_pcm_pwm_streams':unique_validated,'artifacts':artifacts,
        'elapsed_seconds':time.perf_counter()-started,'python_process_cpu_seconds':time.process_time()-started_cpu}
    result['receipt_sha256']=sha(canonical(result));save(result_path,result)
    return {'id':record_id,'cached':False,'records':3,'seconds':result['elapsed_seconds']}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('manifest',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--workers',type=int,default=3);parser.add_argument('--record',type=int);parser.add_argument('--limit',type=int)
    args=parser.parse_args();output=checked_output(args.output)
    if args.output.is_symlink():raise ValueError('Output directory cannot be a symlink')
    if args.record is not None:
        print(json.dumps(worker(args.manifest,output,args.record)),flush=True);return
    if not 1<=args.workers<=3:raise ValueError('workers must be1..3')
    raw=args.manifest.read_bytes();manifest=json.loads(raw);rows=manifest['records']
    if len(rows)!=98 or len({r['private_case_id'] for r in rows})!=49:raise ValueError('Expected complete49case/98profile manifest')
    if args.limit is not None and not 1<=args.limit<=98:raise ValueError('Explicit partial limit must be1..98')
    output.mkdir(parents=True,exist_ok=True);provenance_path=output/'provenance-private.json'
    protect_outputs([args.manifest,Path(__file__),*[Path(r['reference']['path']) for r in rows],*[Path(s['path']) for r in rows for s in r['segments']]],
        [provenance_path,output/'progress-private.json',*[output/f'fixed-{i+1:03d}'/'results-private.json' for i in range(len(rows))]])
    binding=source_binding();libraries={}
    for name,compact_only in (('common',False),('v5',True)):
        with BatchSession('batch',speech=True,speech_compact=True,compact_only=compact_only) as decoder:
            path=decoder.library_path.resolve();libraries[name]={'path':str(path),'sha256':sha(path.read_bytes())}
    provenance={'schema':'lpx-v5-fixed-fields-corpus-private-v1','manifest_sha256':sha(raw),'binding':binding,'native_libraries':libraries}
    if provenance_path.exists() and load(provenance_path)!=provenance:raise ValueError('Output belongs to a different frozen source/manifest/runtime')
    save(provenance_path,provenance);indices=list(range(len(rows) if args.limit is None else args.limit));active={};done=[]
    env=os.environ.copy();env['PYTHONPATH']=os.pathsep.join(map(str,sys.path));started=time.perf_counter()
    while indices or active:
        while indices and len(active)<args.workers:
            index=indices.pop(0);folder=output/f'fixed-{index+1:03d}';folder.mkdir(exist_ok=True);log=guard_target(folder/'worker.log').open('wb')
            command=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),str(args.manifest.resolve()),str(output), '--record',str(index)]
            process=subprocess.Popen(command,env=env,stdout=log,stderr=subprocess.STDOUT)
            active[index]=(process,log)
        finished=[]
        for index,(process,log) in active.items():
            code=process.poll()
            if code is None:continue
            log.close();finished.append(index)
            if code:
                for other,handle in active.values():
                    if other.poll() is None:other.terminate()
                    handle.close()
                raise RuntimeError(f'Fixed corpus worker{index+1} failed; inspect ignored worker.log')
            done.append(index);print(json.dumps({'complete':len(done),'requested':len(done)+len(indices)+len(active)-len(finished),'id':f'fixed-{index+1:03d}'}),flush=True)
        for index in finished:active.pop(index)
        save(output/'progress-private.json',{'status':'running','complete':sorted(done),'source_binding_sha256':sha(canonical(binding))})
        check_binding(binding,args.manifest,sha(raw));time.sleep(.5)
    check_binding(binding,args.manifest,sha(raw))
    save(output/'progress-private.json',{'status':'complete' if len(done)==98 else 'partial','complete':sorted(done),'source_binding_sha256':sha(canonical(binding)),
        'elapsed_seconds':time.perf_counter()-started})
    print(json.dumps({'status':'complete' if len(done)==98 else 'partial','records':len(done),'elapsed_seconds':time.perf_counter()-started}),flush=True)


if __name__=='__main__':main()
