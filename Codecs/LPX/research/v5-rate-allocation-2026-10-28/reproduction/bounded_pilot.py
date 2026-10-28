"""Same tuning subset, feasible amplitude seed, bounded exact pulse swaps."""
import hashlib,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
import speech_compact as compact
from speech_rate_allocation import bit_accounting,fit_capacity,improve_extras
from enhance_speech_compact import advance
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames
from refine_speech_compact import quality,no_regression
from standard_metrics import pwm_duties
from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes

import argparse
from measure_speech_firmware import checked_output
from output_paths import protect_outputs
_parser=argparse.ArgumentParser(description=__doc__)
_parser.add_argument('manifest',type=Path)
_parser.add_argument('exact_pilot',type=Path)
_parser.add_argument('output',type=Path)
_args=_parser.parse_args()
ROOT=Path.cwd();MANIFEST=_args.manifest.resolve();OLD=checked_output(_args.exact_pilot);OUT=checked_output(_args.output);OUT.mkdir(parents=True,exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
manifest_bytes=MANIFEST.read_bytes();manifest=json.loads(manifest_bytes)
old=json.loads((OLD/'results-private.json').read_text());assert old['status']=='complete' and old['manifest_sha256']==sha(manifest_bytes)
selection=[r for r in old['records'] if r['percent']==100 and r['policy']=='amplitude']
assert len(selection)==6 and {r['id'] for r in selection}=={f'pilot-{i:03d}' for i in range(1,7)}
lookup={(r['private_case_id'],r['profile']):r for r in manifest['records']};records=[];started=time.perf_counter();started_cpu=time.process_time()
sources=source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src')
protect_outputs([MANIFEST,Path(__file__),OLD/'results-private.json']+[Path(r['reference']['path']) for r in manifest['records']]+[Path(s['path']) for r in manifest['records'] for s in r['segments']], [OUT/'results-private.json',OUT/'summary.json']+[OUT/row['id']/f'{pct}-bounded.l4hy' for row in selection for pct in (100,95,90)])
with BatchSession('batch',speech=True,speech_compact=True) as common,BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as v5:
    for selected in selection:
        row=lookup[(selected['private_case_id'],selected['profile'])];public_id=selected['id']
        assert row['split']=='tuning' and len(row['segments'])==1
        folder=OUT/public_id;folder.mkdir(exist_ok=True)
        refpath=Path(row['reference']['path']);assert sha(refpath.read_bytes())==row['reference']['file_sha256']
        reference,rate=sf.read(refpath,dtype='int16');assert rate==8000 and reference.ndim==1 and len(reference)==row['samples']
        assert sha(reference.astype('<i2').tobytes())==row['reference']['pcm16_sha256'];ref64=reference.astype(np.int64)
        segment=row['segments'][0];blob=Path(segment['path']).read_bytes();assert sha(blob)==segment['stream_sha256']
        values=compact.unpack(blob);n,profile,sp,params,pulses,pre,bright,extras=values;extras=np.asarray(extras,np.int64)
        assert n==len(reference);shift=5 if profile==4 else 4
        vectors=[[(int(v)<<shift)+(1<<(shift-1)) for v in vector] for vector in sp for _ in range(2)]
        co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n);steps=table('scale_table.inc');pp=np.asarray(params,np.int64);ii=np.asarray(pulses,np.int64)
        def render(ee):return advance(co,pp,ii,ee,steps,pre,bright,0,n,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))[0]
        def objective(pcm):return int(np.sum((ref64-pcm.astype(np.int64))**2))
        def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
        layout=bit_accounting(sp,profile,extras)
        for budget in row['budgets']:
            percent=budget['percent'];cap=budget['max_complete_stream_bytes'];assert cap==len(blob)*percent//100
            control,_,size,_=fit_capacity(layout['spectrum_bits'],len(sp),profile,extras,cap,0,n)
            control_stream=serialize(control);control_pcm=render(control);control_metrics=quality(reference,control_pcm)
            before=next(r for r in old['records'] if r['id']==public_id and r['percent']==percent and r['policy']=='amplitude')
            assert len(control_stream)==size==before['file_bytes'] and control_metrics==before['metrics']
            predicate_calls=[0]
            def admissible(pcm):
                predicate_calls[0]+=1
                return no_regression(quality(reference,pcm),control_metrics)
            start=time.perf_counter();cpu=time.process_time()
            result=improve_extras(sp,profile,extras,cap,stop=n,render=render,objective=objective,serialize=serialize,
                max_evaluations=128,candidate_batch=32,admissible=admissible)
            assert result.feasible==(size<=cap) and result.file_bytes==size and result.evaluations<=128
            assert result.quality_admissible and result.score<=objective(control_pcm)
            for stream,pcm in ((result.stream,result.pcm),(control_stream,control_pcm)):
                np.testing.assert_array_equal(compact.decode_model(stream),pcm)
                for decoder in (common,v5):
                    np.testing.assert_array_equal(decoder.decode_one_s16(stream,n),pcm)
                    np.testing.assert_array_equal(decoder.decode_one(stream,n),pwm_duties(pcm))
            metrics=quality(reference,result.pcm);assert no_regression(metrics,control_metrics)
            path=folder/f'{percent}-bounded.l4hy';path.write_bytes(result.stream)
            record={'id':public_id,'profile':profile,'cohort':row['cohort'],'split':'tuning','samples':n,'percent':percent,
                'baseline_bytes':len(blob),'cap':cap,'file_bytes':size,'fits':result.feasible,'status':result.status,
                'amplitude':control_metrics,'bounded':metrics,'removed':result.removed,'accepted_swaps':result.accepted_swaps,
                'evaluations':result.evaluations,'candidate_evaluations':result.candidate_evaluations,'confirmation_evaluations':result.confirmation_evaluations,
                'quality_predicate_calls':predicate_calls[0],'rejected_by_admissible':result.rejected_by_admissible,
                'seed_admissible':result.seed_admissible,'quality_admissible':result.quality_admissible,'trace':result.trace,
                'seconds':time.perf_counter()-start,'python_process_cpu_seconds':time.process_time()-cpu,
                'native_common_v5_model_pcm_pwm_exact':True,'private_case_id':row['private_case_id'],'stream_path':str(path),'stream_sha256':sha(result.stream)}
            records.append(record);(OUT/'results-private.json').write_text(json.dumps({'status':'running','records':records},indent=2)+'\n')
            print(json.dumps({key:record[key] for key in ('id','percent','fits','status','accepted_swaps','evaluations','rejected_by_admissible')}),flush=True)
assert MANIFEST.read_bytes()==manifest_bytes and source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src')==sources
summary={'schema':'lpx-v5-bounded-allocation-pilot-v1','status':'complete','source_commit':'5865df33','decoder_sources':sources,
    'manifest_sha256':sha(manifest_bytes),'pilot_source_sha256':sha(Path(__file__).read_bytes()),'records':len(selection),'rows':len(records),
    'scope':'Same six one-segment tuning recordings as exact-greedy pilot, both profiles, full original length/gain. Fixed spectra/params/base pulses/filters; amplitude seed;128-render bound,32-candidate batches. Accepted swaps preserve amplitude-control PCM/PWM SSE/STOI floors. Original strong-baseline admission remains separate. No evaluation/additional cohort, perceptual or firmware claim.',
    'elapsed_seconds':time.perf_counter()-started,'python_process_cpu_seconds':time.process_time()-started_cpu,
    'cpu_scope':'Python process CPU includes in-process native decoder, synthesis and metrics; compiler subprocess CPU is excluded. Wall time includes selected-output verification.',
    'groups':[]}
for percent in (100,95,90):
    rows=[r for r in records if r['percent']==percent];fitted=[r for r in rows if r['fits']]
    summary['groups'].append({'percent':percent,'records':len(rows),'amplitude_fits':sum(r['file_bytes']<=r['cap'] for r in rows),'bounded_fits':sum(r['fits'] for r in rows),
      'original_cap_fits_better_equal_worse':[sum((r['bounded']['pcm16']['error_energy']<r['amplitude']['pcm16']['error_energy']) if k==0 else (r['bounded']['pcm16']['error_energy']==r['amplitude']['pcm16']['error_energy']) if k==1 else (r['bounded']['pcm16']['error_energy']>r['amplitude']['pcm16']['error_energy']) for r in fitted) for k in range(3)],
      'all_four_amplitude_control_floors_preserved':all(no_regression(r['bounded'],r['amplitude']) for r in rows),
      'accepted_swaps':sum(r['accepted_swaps'] for r in rows),'render_evaluations':sum(r['evaluations'] for r in rows),'wall_seconds':sum(r['seconds'] for r in rows)})
(OUT/'results-private.json').write_text(json.dumps({'status':'complete','manifest_sha256':sha(manifest_bytes),'records':records},indent=2)+'\n')
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
