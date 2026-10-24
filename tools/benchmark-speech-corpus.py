#!/usr/bin/env python3
"""Benchmark the unchanged 406-byte HQ4 numerical core on a prepared corpus.

Prepared reference levels, DC and every sample are preserved. Size includes
actual stream bytes plus code/EOF/alignment estimates, never AVR qualification.
"""
import argparse
from collections import Counter
from copy import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

import numpy as np
from pystoi import stoi
import soundfile as sf
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from new_hq4_encoder import initial_model,search,validate_reference,DECODER_BYTES,MAX_STREAM_BYTES
from hq4_core import pack_stream,unpack_stream
from hq4_speech_search import deterministic_estoi
from model import decode
from spectrogram_objective import SpectrogramObjective
from harmonic_tracks import HarmonicTrackObjective
from partial_bounds import check_partial_bounds
from speech_regression import guard_recordings


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')


def flash_estimate(stream_bytes):
    unpadded = DECODER_BYTES+int(stream_bytes)+1
    return dict(code_bytes=DECODER_BYTES,stream_bytes=int(stream_bytes),eof_bytes=1,
                alignment_bytes=unpadded%2,estimated_flash_bytes=unpadded+unpadded%2,
                fits_estimated_1024=unpadded+unpadded%2 <= 1024,eeprom_bytes=0,
                avr_assembled=False,avr_verified=False,hardware_tested=False,
                policy='Actual packed stream plus frozen code/EOF/alignment estimate; not AVR qualified')


def signal_stats(audio):
    audio = np.asarray(audio,dtype=float)
    rms = float(np.sqrt(np.mean(audio*audio)))
    peak = float(np.max(abs(audio)))
    return dict(samples=len(audio),mean=float(np.mean(audio)),rms=rms,peak=peak,
                positive_peak=float(np.max(audio)),negative_peak=float(np.min(audio)),
                crest_factor=peak/max(rms,1e-30),samples_abs_ge_one=int(np.sum(abs(audio)>=1.)),
                nonfinite_samples=int(np.sum(~np.isfinite(audio))))


def select_entries(manifest,subset,ids=None):
    if manifest.get('schema') != 'micromusic-speech-corpus-v1' or manifest.get('sample_rate') != 7500:
        raise ValueError('Expected micromusic-speech-corpus-v1 at 7500 Hz')
    variant = {'short':'center2048','full':'full'}[subset]
    selected = [entry for entry in manifest['clips'] if entry['variant'] == variant]
    if ids:
        ids = set(ids)
        found = set()
        result = []
        for entry in selected:
            matches = ids & {entry['id'],entry['source_clip_id']}
            if matches:
                result.append(entry);found.update(matches)
        if found != ids:
            raise ValueError('Requested IDs absent from selected subset: '+', '.join(sorted(ids-found)))
        selected = result
    if not selected or len({entry['id'] for entry in selected}) != len(selected):
        raise ValueError('Selected corpus must contain nonempty, unique recording IDs')
    return selected


def reference_path(entry,references_root):
    root = Path(references_root).resolve()
    relative = Path(entry['reference'])
    path = (root/relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root):
        raise ValueError('Reference path must remain relative to references root')
    return path


def roundtrip(frames,durations):
    payload = pack_stream(frames,durations)
    f,d = unpack_stream(payload)
    pcm = decode(frames,durations,0)
    if payload != pack_stream(f,d) or not np.array_equal(pcm,decode(f,d,0)):
        raise AssertionError('Independent HQ4 unpack/repack changed stream or full PCM')
    return payload,pcm


def benchmark_entry(entry,references_root,output,*,proposals=0,seed=23105,stream_budget=MAX_STREAM_BYTES):
    metadata = {key:entry[key] for key in ('id','source_id','source_clip_id','base_clip_id','language','voice',
        'speaker','split','condition','variant','reference','reference_sha256','samples','unpadded_samples',
        'sample_rate','duration_seconds','source_start_seconds','source_relative_start_seconds') if key in entry}
    row = dict(metadata=metadata,status='failed',metrics=None,avr_qualified=False)
    started = time.perf_counter()
    stage = 'reference'
    try:
        path = reference_path(entry,references_root)
        if sha(path.read_bytes()) != entry['reference_sha256']:
            raise ValueError('Prepared reference hash mismatch')
        reference,sr = sf.read(path,dtype='float64')
        if len(reference) != entry['samples'] or sr != entry['sample_rate']:
            raise ValueError('Prepared reference sample count/rate mismatch')
        validate_reference(reference,sr)
        row['reference_signal'] = signal_stats(reference)
        stage = 'initialize'
        (frames,durations,initial_score,settings),trials = initial_model(reference,stream_budget=stream_budget)
        training = dict(proposals=0,initial=initial_score,final=initial_score)
        if proposals:
            frames,durations,training = search(reference,frames,durations,proposals=proposals,
                                               seed=seed,stream_budget=stream_budget)
        stage = 'roundtrip'
        payload,pcm = roundtrip(frames,durations)
        if len(pcm) != len(reference):
            raise AssertionError('Decoded phrase sample count changed')
        audio = (pcm.astype(float)-128)/128
        stage = 'measure'
        tracks = HarmonicTrackObjective(reference,sr)
        detail = tracks.details(audio)
        raw_tracks = copy(tracks)
        raw_tracks.matched = lambda value:sosfilt(raw_tracks.hp,np.asarray(value,dtype=float))
        raw_detail = raw_tracks.details(audio)
        metrics = dict(stoi=float(stoi(reference,audio,sr)),estoi=deterministic_estoi(reference,audio,sr),
                       **SpectrogramObjective(reference,sr).evaluate(audio))
        if not all(np.isfinite(value) for value in metrics.values()):
            raise ValueError('Nonfinite quality metric')
        model = dict(schema='hq4-corpus-baseline-v1',recording_id=entry['id'],sample_rate=sr,samples=len(reference),
                     reference_sha256=entry['reference_sha256'],frames=frames.tolist(),durations=durations.tolist(),
                     stream_sha256=sha(payload),pcm_u8_sha256=sha(pcm.tobytes()),decoder='frozen HQ4 signed-byte lattice')
        dest = output/'models'/entry['id']
        save_json(dest/'model.json',model)
        (dest/'speech.hq').write_bytes(payload)
        (dest/'expected.raw').write_bytes(pcm.tobytes())
        sf.write(dest/'decoded.wav',audio,sr,subtype='FLOAT')
        row.update(status='complete',metrics=metrics,raw_output_signal=signal_stats(audio),
                   output_rms_over_reference_rms=float(np.sqrt(np.mean(audio**2))/max(np.sqrt(np.mean(reference**2)),1e-30)),
                   output_mean_signed_pwm=float(np.mean(pcm.astype(float)-128)),
                   output_pwm_endpoints=int(np.sum((pcm==0)|(pcm==255))),
                   steps_ge_48_pwm=int(np.sum(abs(np.diff(pcm.astype(np.int16)))>=48)),
                   harmonic_metrics=detail['metrics'],raw_harmonic_metrics=raw_detail['metrics'],
                   strict_5db_bounds=check_partial_bounds(raw_detail,
                       max_level_error_db=5.,duration_seconds=len(reference)/sr),
                   level_matched_strict_5db_bounds=check_partial_bounds(detail,
                       max_level_error_db=5.,duration_seconds=len(reference)/sr),
                   size=flash_estimate(len(payload)),stream_sha256=sha(payload),pcm_u8_sha256=sha(pcm.tobytes()),
                   roundtrip_pcm_exact=True,initialization=dict(selected=settings,candidate_trials=len(trials)),
                   training=training,model_reference=f'models/{entry["id"]}/model.json')
    except Exception as error:
        # File paths are kept as manifest-relative identifiers, never copied
        # from machine-specific OS exception messages into retained reports.
        safe_message = (str(error) if isinstance(error,(ValueError,AssertionError)) else 'Operation failed; inspect stage and relative reference identifier')
        row.update(status='infeasible' if stage == 'initialize' and isinstance(error,ValueError) else 'failed',
                   error=dict(stage=stage,type=type(error).__name__,message=safe_message))
    row['elapsed_seconds'] = round(time.perf_counter()-started,6)
    return row


def aggregate(rows):
    result = {}
    for field in ('language','split','condition'):
        result[field] = {}
        for group in sorted({row['metadata'].get(field,'unknown') for row in rows}):
            selected = [row for row in rows if row['metadata'].get(field,'unknown') == group]
            complete = [row for row in selected if row['status'] == 'complete']
            summaries = {}
            for metric in ('stoi','estoi','fine_log_error','envelope_error','unsupported_energy','missing_energy'):
                values = [row['metrics'][metric] for row in complete]
                summaries[metric] = (dict(count=len(values),mean=float(np.mean(values)),minimum=min(values),maximum=max(values))
                                     if values else dict(count=0,mean=None,minimum=None,maximum=None))
            result[field][group] = dict(recordings=len(selected),status_counts=dict(Counter(row['status'] for row in selected)),
                                       metrics=summaries)
    return result


def compare_reports(baseline,candidate):
    old_rows = {row['metadata']['id']:row for row in baseline['clips']}
    new_rows = {row['metadata']['id']:row for row in candidate['clips']}
    violations,invalid_ids = [],set()
    for field in ('manifest_sha256','subset','signal_policy'):
        if field not in baseline or field not in candidate or baseline[field] != candidate[field]:
            violations.append(dict(field=field,reason='missing_or_changed_reference_policy'))
            invalid_ids.update(set(old_rows)|set(new_rows))
    if set(old_rows) != set(new_rows):
        violations.append(dict(field='recording_ids',reason='different_recording_selection'))
    for ident in sorted(set(old_rows)&set(new_rows)):
        before,after = old_rows[ident]['metadata'],new_rows[ident]['metadata']
        for field in ('reference_sha256','samples','sample_rate'):
            if field not in before or field not in after or before[field] != after[field]:
                violations.append(dict(id=ident,field=field,reason='missing_or_changed_reference'))
                invalid_ids.add(ident)
    old = {ident:row['metrics'] if row['status'] == 'complete' else None for ident,row in old_rows.items()}
    new = {ident:row['metrics'] if row['status'] == 'complete' and ident not in invalid_ids else None
           for ident,row in new_rows.items()}
    result = guard_recordings(old,new,sorted(set(old)|set(new)),fallback_to_baseline=False)
    result['reference_invariants_passed'] = not bool(violations)
    result['reference_invariant_violations'] = violations
    result['candidate_passed'] = result['candidate_passed'] and not bool(violations)
    result['selection_passed'] = result['selection_passed'] and not bool(violations)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--references-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--subset',choices=('full','short'),default='short')
    p.add_argument('--ids',nargs='+')
    p.add_argument('--proposals',type=int,default=0)
    p.add_argument('--seed',type=int,default=23105)
    p.add_argument('--stream-budget',type=int,default=MAX_STREAM_BYTES)
    p.add_argument('--baseline-report',type=Path,help='Compare this run per recording against an earlier baseline report')
    p.add_argument('--retain',type=Path,help='Copy only report/models into a research directory; no audio/raw/stream binaries')
    a = p.parse_args()
    if a.proposals < 0 or not 8 <= a.stream_budget <= MAX_STREAM_BYTES:
        p.error('Invalid proposal/stream budget')
    manifest = json.loads(a.manifest.read_text(encoding='utf-8'))
    entries = select_entries(manifest,a.subset,a.ids)
    sources = [Path(__file__)]+[CODEC/name for name in ('new_hq4_encoder.py','model.py','hq4_core.py',
        'hq4_speech_search.py','auto_encoder.py','spectrogram_objective.py','harmonic_tracks.py','partial_bounds.py','speech_regression.py')]
    fingerprints = {path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources}
    report = dict(schema='speech-corpus-benchmark-v1',manifest_sha256=sha(a.manifest.read_bytes()),subset=a.subset,
        requested_ids=a.ids,encoder='unchanged HQ4 automatic initialization',proposals=a.proposals,seed=a.seed,
        stream_budget=a.stream_budget,avr_qualified=False,hardware_tested=False,
        signal_policy='Unchanged prepared samples, level and DC; no output normalization before raw signal statistics',
        metric_policy='STOI/eSTOI plus global-level-matched spectral/tracking diagnostics; primary strict bounds use raw level, matched bounds separately named',
        aggregate_policy='Descriptive summaries only; regression decisions are per recording and per metric',
        source_sha256_normalized_lf=fingerprints,
        runtime={name:importlib.metadata.version(name) for name in ('numpy','scipy','numba','soundfile','pystoi')},clips=[])
    report['runtime']['python'] = sys.version.split()[0]
    a.output.mkdir(parents=True,exist_ok=True)
    for entry in entries:
        row = benchmark_entry(entry,a.references_root,a.output,proposals=a.proposals,seed=a.seed,stream_budget=a.stream_budget)
        report['clips'].append(row)
        report['aggregates'] = aggregate(report['clips'])
        report['complete_selection'] = len(report['clips']) == len(entries)
        save_json(a.output/'report.json',report)
        print(json.dumps(dict(id=entry['id'],status=row['status'],elapsed_seconds=row['elapsed_seconds'],metrics=row['metrics'])),flush=True)
    if any(sha((ROOT/name).read_text(encoding='utf-8').encode()) != value for name,value in fingerprints.items()):
        raise RuntimeError('Benchmark source changed during run; report is not a frozen-source baseline')
    if a.baseline_report:
        old = json.loads(a.baseline_report.read_text(encoding='utf-8'))
        report['comparison'] = compare_reports(old,report)
        report['comparison_baseline_sha256'] = sha(a.baseline_report.read_bytes())
        save_json(a.output/'report.json',report)
    if a.retain:
        save_json(a.retain/'report.json',report)
        for row in report['clips']:
            if row['status'] == 'complete':
                relative = Path(row['model_reference'])
                save_json(a.retain/relative,json.loads((a.output/relative).read_text(encoding='utf-8')))


if __name__ == '__main__':
    main()
