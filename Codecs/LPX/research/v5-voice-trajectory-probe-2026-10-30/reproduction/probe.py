"""One fixed-size trajectory call per declared saved seed; no initial fits."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time
import traceback
from unittest.mock import patch

import numpy as np
import soundfile as sf
import speech_compact as compact
import speech_v4
from batch_decoder import BatchSession
from encode_speech_voice import _quality
from refine_speech_compact import no_regression
from refine_speech_trajectory import refine
from speech_noise_objective import NoiseObjective
from standard_metrics import pwm_duties,pwm_pcm16
from voice_character import track_pitch,compare_voice

SETTINGS = dict(frame_limit=8,window_frames=2,beam_width=3,spectral_candidates=2,
    excitation_candidates=2,excitation_horizon=160,max_evaluations=128,
    selection='conservative',capacity_policy='none',allocation_evaluations=0,
    rate_lambda=0.,screening='local',screening_horizon=640,speech=True)


def endpoint_streams(seed,selected,raw,frontier):
    """Read the existing refiner's dictionary export, retaining input order."""
    streams=[seed]+[b for b in (selected,raw) if b is not None]
    for point in frontier:
        if not isinstance(point,dict) or not isinstance(point.get('stream'),(bytes,bytearray)):
            raise ValueError('Unexpected trajectory frontier export')
        streams.append(point['stream'])
    return list(dict.fromkeys(map(bytes,streams)))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','producer-study','reference','v1-control','adaptive-control','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--prior-failure',type=Path)
    args=parser.parse_args()
    root,out=args.source_root.resolve(),args.output.resolve()
    if not out.is_relative_to(root/'build') or out.exists():
        raise ValueError('Use fresh private output under source-root/build')
    out.mkdir(parents=True)
    try:
        producer=json.loads((args.producer_study/'binding-private.json').read_text())
        def guard():
            for relative,digest in producer['core'].items():
                if sha((root/relative).read_bytes()) != digest:
                    raise ValueError('Frozen source changed')
        guard()
        target,rate=sf.read(args.reference,dtype='int16')
        seeds=[('v1',args.v1_control.read_bytes()),('adaptive',args.adaptive_control.read_bytes())]
        adaptive_marker=json.loads((args.producer_study/'cap-1800/complete-private.json').read_text())
        if (rate!=8000 or target.ndim!=1 or len(target)!=32000
                or sha(target.astype('<i2').tobytes())!=producer['target_sha256']
                or [len(b) for _,b in seeds]!=[1702,1710]
                or sha(seeds[0][1])!=producer['control_sha256']
                or sha(seeds[1][1])!=adaptive_marker['selected_sha256']
                or not adaptive_marker['guard_pass']):
            raise ValueError('Declared target or seed geometry differs')
        for _,blob in seeds:
            if compact.unpack(blob)[:2]!=(32000,4):
                raise ValueError('Expected declared profile-4 seeds')
        protocol=Path(__file__).resolve().parents[1]/'PROTOCOL.md'
        source_bytes=Path(__file__).read_bytes()
        prior=None
        if args.prior_failure is not None:
            prior_binding=json.loads((args.prior_failure/'binding-private.json').read_text())
            failure=json.loads((args.prior_failure/'failure-private.json').read_text())
            if (prior_binding['settings']!=SETTINGS or prior_binding['seed_sha256']!=[sha(b) for _,b in seeds]
                    or failure['exception']!='AttributeError' or "point.stream" not in failure['traceback']):
                raise ValueError('Unexpected prior failed probe')
            prior=dict(path=str(args.prior_failure.resolve()),failed_postprocessing_attempts=1,
                binding_sha256=sha((args.prior_failure/'binding-private.json').read_bytes()),
                failure_sha256=sha((args.prior_failure/'failure-private.json').read_bytes()),
                completed_target_helper_calls=1,inner_evaluation_count_known=False,
                inner_evaluation_upper_bound=SETTINGS['max_evaluations'])
        save(out/'binding-private.json',dict(producer=producer,settings=SETTINGS,prior_failure=prior,
            source_sha256=sha(source_bytes),protocol_sha256=sha(protocol.read_bytes()),
            reference_sha256=producer['target_sha256'],seed_sha256=[sha(b) for _,b in seeds]))
        track=track_pitch(target)
        noise=NoiseObjective(target,track.period)
        voice=noise.voice_objective
        def objective(pcm):
            return float(np.mean([voice(x)+noise(x) for x in (pcm,pwm_pcm16(pcm))]))
        with BatchSession('batch',speech=True,speech_compact=True) as common,BatchSession(
                'batch',speech=True,speech_compact=True,compact_only=True) as only,ExitStack() as stack:
            def forbidden(*a,**kw):
                raise AssertionError('Fresh seed fitting is forbidden')
            stack.enter_context(patch.object(speech_v4,'encode',forbidden))
            for role,seed in seeds:
                folder=out/role
                folder.mkdir()
                save(folder/'attempt-private.json',dict(status='started',settings=SETTINGS,
                    complete_byte_cap=len(seed),new_seed_fits=0))
                frontier=[]
                start_wall,start_cpu=time.perf_counter(),time.process_time()
                save(folder/'helper-start-private.json',dict(helper_calls_started=1,new_seed_fits=0))
                selected,_,detail,raw=refine(target,seed,common,len(seed),objective=objective,
                    objective_name='voice_noise_pcm_pwm_frozen_v2',frontier=frontier,**SETTINGS)
                wall,cpu=time.perf_counter()-start_wall,time.process_time()-start_cpu
                save(folder/'helper-return-private.json',dict(report=detail,helper_calls_completed=1,
                    wall_seconds=wall,cpu_seconds=cpu))
                blobs=endpoint_streams(seed,selected,raw,frontier)
                rows=[]
                for index,blob in enumerate(blobs):
                    pcm=compact.decode_model(blob)
                    for receiver in (common,only):
                        actual,duty=receiver.decode_one_s16(blob,len(target)),receiver.decode_one(blob,len(target))
                        if actual is None or duty is None or not np.array_equal(actual,pcm) or not np.array_equal(duty,pwm_duties(pcm)):
                            raise AssertionError('Endpoint native/model mismatch')
                    (folder/('endpoint-%03d.l4hy'%index)).write_bytes(blob)
                    sf.write(folder/('endpoint-%03d.wav'%index),pcm,8000,subtype='PCM_16')
                    rows.append(dict(id=index,file_bytes=len(blob),score=objective(pcm),
                        metrics=_quality(target,pcm,True),voice=compare_voice(target,pcm,reference_track=track),
                        pwm_voice=compare_voice(target,pwm_pcm16(pcm),reference_track=track),
                        clipped_samples=int(np.count_nonzero((pcm<=-32768)|(pcm>=32767)))))
                baseline=rows[0]
                for row in rows:
                    row['outer_admissible']=bool(row['file_bytes']<=len(seed)
                        and no_regression(row['metrics'],baseline['metrics'])
                        and row['score']<=baseline['score']+1e-12
                        and row['clipped_samples']<=baseline['clipped_samples']
                        and all(row[k]['within_tolerance_frames']>=baseline[k]['within_tolerance_frames']
                                for k in ('voice','pwm_voice')))
                eligible=[r for r in rows if r['outer_admissible']]
                winner=min(eligible,key=lambda r:(r['score'],r['file_bytes'],r['id']))
                guard()
                if (Path(__file__).read_bytes()!=source_bytes or
                        sha(protocol.read_bytes())!=json.loads((out/'binding-private.json').read_text())['protocol_sha256']):
                    raise ValueError('Executing probe source changed')
                save(folder/'report-private.json',dict(role=role,rows=rows,selected_endpoint=winner['id'],
                    helper=detail,wall_seconds=wall,cpu_seconds=cpu,new_seed_fits=0,
                    helper_selected_endpoint=None if selected is None else blobs.index(selected),
                    raw_endpoint=None if raw is None else blobs.index(raw)))
                save(folder/'complete-private.json',dict(status='complete',new_seed_fits=0,
                    winner_sha256=sha(blobs[winner['id']]),source_input_guards_pass=True,
                    artifacts_sha256={p.name:sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()}))
                print(json.dumps(dict(role=role,status='complete',bytes=winner['file_bytes'],
                    changed=winner['id']!=0,score_before=baseline['score'],score_after=winner['score'])),flush=True)
        return 0
    except Exception as exc:
        save(out/'failure-private.json',dict(exception=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='failed',exception=type(exc).__name__)),flush=True)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
