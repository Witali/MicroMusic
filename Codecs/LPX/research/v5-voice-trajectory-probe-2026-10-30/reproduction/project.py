"""Recheck completed diagnostic endpoints; no encoding or refinement."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from batch_decoder import BatchSession
import speech_compact as compact
from encode_speech_voice import _quality
from refine_speech_compact import no_regression
from speech_noise_objective import NoiseObjective
from standard_metrics import pwm_duties,pwm_pcm16
from voice_character import track_pitch,compare_voice


def sha(data):
    return hashlib.sha256(data).hexdigest()


def same(actual,expected):
    if isinstance(expected,dict):
        for key,value in expected.items():same(actual[key],value)
    elif isinstance(expected,float):
        if not np.isfinite(actual) or abs(actual-expected)>1e-12:raise AssertionError('Numeric projection differs')
    elif actual!=expected:raise AssertionError('Projection claim differs')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','study','reference','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use fresh output')
    binding=json.loads((args.study/'binding-private.json').read_text())
    core=binding['producer']['core']
    for relative,digest in core.items():
        if sha((args.source_root/relative).read_bytes())!=digest:raise AssertionError('Core changed')
    here=Path(__file__).resolve().parent
    if sha((here/'probe.py').read_bytes())!=binding['source_sha256']:raise AssertionError('Probe source changed')
    if sha((here.parent/'PROTOCOL.md').read_bytes())!=binding['protocol_sha256']:raise AssertionError('Protocol changed')
    prior=binding['prior_failure']
    for name,key in (('binding-private.json','binding_sha256'),('failure-private.json','failure_sha256')):
        if sha((Path(prior['path'])/name).read_bytes())!=prior[key]:raise AssertionError('Prior failure changed')
    ref,rate=sf.read(args.reference,dtype='int16')
    if rate!=8000 or sha(ref.astype('<i2').tobytes())!=binding['reference_sha256']:raise AssertionError('Reference changed')
    track=track_pitch(ref);noise=NoiseObjective(ref,track.period);voice=noise.voice_objective
    results=[];checks=0
    with BatchSession('batch',speech=True,speech_compact=True) as common,BatchSession(
            'batch',speech=True,speech_compact=True,compact_only=True) as only:
        for role in ('v1','adaptive'):
            folder=args.study/role
            marker=json.loads((folder/'complete-private.json').read_text())
            for name,digest in marker['artifacts_sha256'].items():
                if sha((folder/name).read_bytes())!=digest:raise AssertionError('Endpoint artifact changed')
            report=json.loads((folder/'report-private.json').read_text())
            rows=[]
            for index,claim in enumerate(report['rows']):
                blob=(folder/('endpoint-%03d.l4hy'%index)).read_bytes();pcm=compact.decode_model(blob)
                for receiver in (common,only):
                    for actual,wanted in ((receiver.decode_one_s16(blob,len(ref)),pcm),
                            (receiver.decode_one(blob,len(ref)),pwm_duties(pcm))):
                        if actual is None or not np.array_equal(actual,wanted):raise AssertionError('Native output differs')
                        checks+=1
                score=float(np.mean([voice(x)+noise(x) for x in (pcm,pwm_pcm16(pcm))]))
                row=dict(id=index,file_bytes=len(blob),score=score,metrics=_quality(ref,pcm,True),
                    voice=compare_voice(ref,pcm,reference_track=track),
                    pwm_voice=compare_voice(ref,pwm_pcm16(pcm),reference_track=track),
                    clipped_samples=int(np.count_nonzero((pcm<=-32768)|(pcm>=32767))))
                base=row if index==0 else rows[0]
                row['outer_admissible']=bool(len(blob)<=base['file_bytes'] and row['score']<=base['score']+1e-12
                    and no_regression(row['metrics'],base['metrics']) and row['clipped_samples']<=base['clipped_samples']
                    and all(row[k]['within_tolerance_frames']>=base[k]['within_tolerance_frames'] for k in ('voice','pwm_voice')))
                same(claim,row);rows.append(row)
            winner=min((r for r in rows if r['outer_admissible']),key=lambda r:(r['score'],r['file_bytes'],r['id']))
            if winner['id']!=report['selected_endpoint']:raise AssertionError('Endpoint choice differs')
            helper={k:report['helper'][k] for k in ('full_synthesis_evaluations','objective_evaluations',
                'local_synthesis_evaluations','local_synthesized_samples','spectral_trials','excitation_trials',
                'serialization_calls','final_metric_evaluations','search_limit_reached')}
            results.append(dict(role=role,rows=rows,selected_endpoint=winner['id'],helper=helper,
                wall_seconds=report['wall_seconds'],cpu_seconds=report['cpu_seconds']))
    result=dict(schema='lpx-voice-trajectory-probe-v1',settings=binding['settings'],cases=results,
        native_domain_comparisons=checks,native_sample_domain_comparisons=checks*len(ref),
        target_helper_calls=3,retained_helper_reports=2,failed_postprocessing_attempts=1,new_seed_fits=0,
        first_call_inner_counters='unknown; at most128 full renders, no recovered local/objective/CPU counts',
        known_full_render_evaluations=sum(r['helper']['full_synthesis_evaluations'] for r in results),
        source_code_sha256=core,probe_source_sha256=binding['source_sha256'],protocol_sha256=binding['protocol_sha256'],
        no_production_integration=True,new_player_images=0,
        scope='Two seed views of one tuning source; no global/perceptual/corpus/general real-time claim; prior cost is retained as unknown.')
    with args.output.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(status='pass',cases=2,native_domains=checks)))


if __name__=='__main__':main()
