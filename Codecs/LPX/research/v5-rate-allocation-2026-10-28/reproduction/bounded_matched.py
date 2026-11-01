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

import argparse
from measure_speech_firmware import checked_output
from output_paths import protect_outputs
_parser=argparse.ArgumentParser(description=__doc__)
_parser.add_argument('manifest',type=Path)
_parser.add_argument('exact_pilot',type=Path)
_parser.add_argument('bounded_pilot',type=Path)
_args=_parser.parse_args()
ROOT=Path.cwd();OLD=checked_output(_args.exact_pilot);OUT=checked_output(_args.bounded_pilot);manifest=json.loads(_args.manifest.read_text())
lookup={(r['private_case_id'],r['profile']):r for r in manifest['records']}
original=json.loads((OLD/'results-private.json').read_text())['records']
points=json.loads((OLD/'matched-size.json').read_text())['rows'];rows=[];started=time.perf_counter()
protect_outputs([_args.manifest,Path(__file__),OLD/'results-private.json',OLD/'matched-size.json']+[Path(s['path']) for r in manifest['records'] for s in r['segments']], [OUT/'matched-size.json'])
with BatchSession('batch',speech=True,speech_compact=True) as common,BatchSession('batch',speech=True,speech_compact=True,compact_only=True) as v5:
 for point in points:
    selected=next(r for r in original if r['id']==point['id']);row=lookup[(selected['private_case_id'],point['profile'])]
    assert row['split']=='tuning' and len(row['segments'])==1
    reference,rate=sf.read(row['reference']['path'],dtype='int16');ref64=reference.astype(np.int64);assert rate==8000
    values=compact.unpack(Path(row['segments'][0]['path']).read_bytes());n,profile,sp,params,pulses,pre,bright,extras=values
    extras=np.asarray(extras,np.int64);shift=5 if profile==4 else 4
    vectors=[[(int(v)<<shift)+(1<<(shift-1)) for v in vector] for vector in sp for _ in range(2)]
    co=coefficient_trace(pack_frames(vectors[:(n+159)//160]),n);steps=table('scale_table.inc');pp=np.asarray(params,np.int64);ii=np.asarray(pulses,np.int64)
    def render(ee):return advance(co,pp,ii,ee,steps,pre,bright,0,n,np.zeros(10,np.int64),0,0,np.zeros(256,np.int64))[0]
    def serialize(ee):return compact.pack(*values[:7],extras=ee)[0]
    def objective(pcm):return int(np.sum((ref64-pcm.astype(np.int64))**2))
    cap=point['file_bytes'];layout=bit_accounting(sp,profile,extras)
    control,_,size,_=fit_capacity(layout['spectrum_bits'],len(sp),profile,extras,cap,0,n)
    baseline=quality(reference,render(control));assert baseline==point['amplitude'] and size==cap
    start=time.perf_counter()
    result=improve_extras(sp,profile,extras,cap,stop=n,render=render,objective=objective,serialize=serialize,
        max_evaluations=128,candidate_batch=32,admissible=lambda pcm:no_regression(quality(reference,pcm),baseline))
    assert result.feasible and result.file_bytes==cap and result.quality_admissible
    metrics=quality(reference,result.pcm);assert no_regression(metrics,baseline)
    np.testing.assert_array_equal(result.pcm,compact.decode_model(result.stream))
    for decoder in (common,v5):
        np.testing.assert_array_equal(decoder.decode_one_s16(result.stream,n),result.pcm)
        np.testing.assert_array_equal(decoder.decode_one(result.stream,n),pwm_duties(result.pcm))
    rows.append({'id':point['id'],'profile':profile,'cohort':point['cohort'],'samples':n,'file_bytes':cap,
        'original_cap_percent':point['original_cap_percent'],'original_cap_fitted':point['original_cap_fitted'],
        'amplitude':baseline,'bounded':metrics,'exact_greedy':point['marginal'],
        'evaluations':result.evaluations,'accepted_swaps':result.accepted_swaps,'status':result.status,
        'quality_admissible':result.quality_admissible,'rejected_by_admissible':result.rejected_by_admissible,
        'seconds':time.perf_counter()-start,'trace':result.trace,'native_common_v5_model_pcm_pwm_exact':True,
        'pcm_sse_change_percent':100*(metrics['pcm16']['error_energy']-baseline['pcm16']['error_energy'])/baseline['pcm16']['error_energy'] if baseline['pcm16']['error_energy'] else 0})
    print(json.dumps({key:rows[-1][key] for key in ('id','evaluations','accepted_swaps','pcm_sse_change_percent')}),flush=True)
summary={'schema':'lpx-v5-bounded-equal-achieved-size-v1','status':'complete','source_commit':'5865df33','rows':rows,
    'comparisons':len(rows),'max_render_evaluations':128,'all_amplitude_four_floors_preserved':True,'elapsed_seconds':time.perf_counter()-started,
    'scope':'Same six tuning records at previously fixed exact-greedy achieved sizes; original95/90cap misses remain misses, never relabeled as admission.',
    'better_equal_worse':[sum((r['bounded']['pcm16']['error_energy']<r['amplitude']['pcm16']['error_energy']) if k==0 else (r['bounded']['pcm16']['error_energy']==r['amplitude']['pcm16']['error_energy']) if k==1 else (r['bounded']['pcm16']['error_energy']>r['amplitude']['pcm16']['error_energy']) for r in rows) for k in range(3)]}
(OUT/'matched-size.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'comparisons':len(rows),'better_equal_worse':summary['better_equal_worse'],'seconds':summary['elapsed_seconds']}))
