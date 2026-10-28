"""Tuning-only bounded exact marginal versus preserved amplitude allocation."""
import hashlib,json,time
from pathlib import Path
import numpy as np
import soundfile as sf
import speech_compact as compact
from speech_rate_allocation import bit_accounting,fit_capacity,reclaim_extras
from enhance_speech_compact import advance
from q0_model import coefficient_trace,table
from wav_lpc import pack_frames
from refine_speech_compact import quality,no_regression
from batch_decoder import BatchSession
from benchmark_speech_flash import source_hashes

import argparse
from measure_speech_firmware import checked_output
from output_paths import protect_outputs
_parser=argparse.ArgumentParser(description=__doc__)
_parser.add_argument('manifest',type=Path)
_parser.add_argument('output',type=Path)
_args=_parser.parse_args()
ROOT=Path.cwd();MANIFEST=_args.manifest.resolve();OUT=checked_output(_args.output);OUT.mkdir(parents=True,exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
manifest_bytes=MANIFEST.read_bytes();manifest=json.loads(manifest_bytes);sources=source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src')
eligible=[r for r in manifest['records'] if r['split']=='tuning' and len(r['segments'])==1 and r['samples']>=8000]
groups={}
for row in eligible:groups.setdefault((row['cohort'],row['private_case_id']),[]).append(row)
selected=[]
for cohort,limit in (('speech',2),('regression',1)):
    choices=[]
    for (group,identity),rows in groups.items():
        if group!=cohort or {r['profile'] for r in rows}!={4,6}:continue
        active=sum(np.count_nonzero(np.asarray(compact.unpack(Path(r['segments'][0]['path']).read_bytes())[7])[:,1]) for r in rows)
        if active:choices.append(rows)
    choices.sort(key=lambda rows:(rows[0]['samples'],min(r['id'] for r in rows)))
    for rows in choices[:limit]:selected.extend(sorted(rows,key=lambda r:r['profile']))
assert len(selected)==6
protect_outputs([MANIFEST,Path(__file__)]+[Path(r['reference']['path']) for r in selected]+[Path(r['segments'][0]['path']) for r in selected], [OUT/'results-private.json',OUT/'summary.json']+[OUT/f'pilot-{i:03d}'/f'{pct}-{policy}.l4hy' for i in range(1,7) for pct in (100,95,90) for policy in ('amplitude','marginal')])
records=[];started=time.perf_counter()
with BatchSession('batch',speech=True,speech_compact=True) as common, BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as v5:
    for ordinal,row in enumerate(selected,1):
        public_id=f'pilot-{ordinal:03d}';folder=OUT/public_id;folder.mkdir(exist_ok=True)
        refpath=Path(row['reference']['path']);assert sha(refpath.read_bytes())==row['reference']['file_sha256']
        reference,rate=sf.read(refpath,dtype='int16');assert rate==8000 and reference.ndim==1 and len(reference)==row['samples']
        assert sha(reference.astype('<i2').tobytes())==row['reference']['pcm16_sha256']
        reference64=reference.astype(np.int64)
        segment=row['segments'][0];blob=Path(segment['path']).read_bytes()
        assert sha(blob)==segment['stream_sha256'] and len(blob)==segment['file_bytes']==row['baseline_bytes']
        values=compact.unpack(blob);n,profile,sp,params,pulses,pre,bright,extras=values
        assert n==len(reference) and profile==row['profile'];extras=np.asarray(extras,np.int64)
        shift=5 if profile==4 else 4
        vectors=[[(int(v)<<shift)+(1<<(shift-1)) for v in vec] for vec in sp for _ in range(2)]
        co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n);steps=table('scale_table.inc')
        pp=np.asarray(params,np.int64);ii=np.asarray(pulses,np.int64)
        def render(ee):return advance(co,pp,ii,ee,steps,pre,bright,0,n,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))[0]
        def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
        def objective(pcm):return int(np.sum((reference64-pcm.astype(np.int64))**2))
        initial=render(extras)
        for pcm in (compact.decode_model(blob),common.decode_one_s16(blob,n),v5.decode_one_s16(blob,n)):np.testing.assert_array_equal(initial,pcm)
        assert sha(initial.astype('<i2').tobytes())==row['baseline_pcm16_sha256']
        baseline=quality(reference,initial);layout=bit_accounting(sp,profile,extras)
        assert layout['file_bytes']==len(serialize(extras))==len(blob)
        for budget in row['budgets']:
            percent=budget['percent'];cap=budget['max_complete_stream_bytes'];assert cap==len(blob)*percent//100
            for policy in ('amplitude','marginal'):
                start=time.perf_counter()
                if policy=='amplitude':
                    added,capacity,size,removed=fit_capacity(layout['spectrum_bits'],len(sp),profile,extras,cap,0,n)
                    pcm=render(added);stream=serialize(added);assert size==len(stream)
                    extra={'status':'fit' if size<=cap else 'no_removable_pulses','removed':removed,'evaluations':1,'trace':[]}
                else:
                    result=reclaim_extras(sp,profile,extras,cap,render=render,objective=objective,serialize=serialize,max_evaluations=1024)
                    added=result.extras;pcm=result.pcm;stream=result.stream;size=result.file_bytes
                    extra={'status':result.status,'removed':result.removed,'evaluations':result.evaluations,'trace':result.trace}
                for actual in (compact.decode_model(stream),common.decode_one_s16(stream,n),v5.decode_one_s16(stream,n)):np.testing.assert_array_equal(pcm,actual)
                metrics=quality(reference,pcm)
                stream_path=folder/f'{percent}-{policy}.l4hy';stream_path.write_bytes(stream)
                record={'id':public_id,'profile':profile,'cohort':row['cohort'],'split':'tuning','samples':n,'percent':percent,'policy':policy,
                    'baseline_bytes':len(blob),'cap':cap,'file_bytes':size,'fits':size<=cap,'baseline':baseline,'metrics':metrics,
                    'conservative_floors_passed':no_regression(metrics,baseline),'extra_pulses_initial':layout['extra_pulses'],
                    'extra_pulses_remaining':int(np.count_nonzero(added[:,1])),'seconds':time.perf_counter()-start,'native_common_v5_model_exact':True,**extra,
                    'private_case_id':row['private_case_id'],'stream_path':str(stream_path),'stream_sha256':sha(stream)}
                records.append(record)
                print(json.dumps({'id':public_id,'percent':percent,'policy':policy,'fits':record['fits'],'status':extra['status'],'evaluations':extra['evaluations']}),flush=True)
                (OUT/'results-private.json').write_text(json.dumps({'status':'running','records':records},indent=2)+'\n')
assert MANIFEST.read_bytes()==manifest_bytes and source_hashes(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/src')==sources
summary={'schema':'lpx-v5-marginal-allocation-pilot-v1','status':'complete','source_commit':'9948ae16','decoder_sources':sources,
    'manifest_sha256':sha(manifest_bytes),'pilot_source_sha256':sha(Path(__file__).read_bytes()),'tuning_records':6,'tuning_cases':3,'rows':len(records),
    'scope':'Tuning only; deterministic shortest one-segment recordings >=8000 samples, two speech cases and one regression case with any active extras, both profiles; SSE objective. Complete original length/gain. 1024-render marginal bound. No evaluation or additional cohort. No firmware admission.',
    'selection_is_perceptual_claim':False,'elapsed_seconds':time.perf_counter()-started,'groups':[]}
for percent in (100,95,90):
    a={r['id']:r for r in records if r['percent']==percent and r['policy']=='amplitude'}
    b={r['id']:r for r in records if r['percent']==percent and r['policy']=='marginal'}
    commonfit=[i for i in a if a[i]['fits'] and b[i]['fits']]
    summary['groups'].append({'percent':percent,'records':len(a),'amplitude_fits':sum(r['fits'] for r in a.values()),'marginal_fits':sum(r['fits'] for r in b.values()),
      'marginal_evaluation_limits':sum(r['status']=='evaluation_limit' for r in b.values()),'common_fit':len(commonfit),
      'marginal_pcm_sse_better_equal_worse':[sum((b[i]['metrics']['pcm16']['error_energy']<a[i]['metrics']['pcm16']['error_energy']) if comparison=='better' else (b[i]['metrics']['pcm16']['error_energy']==a[i]['metrics']['pcm16']['error_energy']) if comparison=='equal' else (b[i]['metrics']['pcm16']['error_energy']>a[i]['metrics']['pcm16']['error_energy']) for i in commonfit) for comparison in ('better','equal','worse')]})
(OUT/'results-private.json').write_text(json.dumps({'status':'complete','manifest_sha256':sha(manifest_bytes),'records':records},indent=2)+'\n')
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
