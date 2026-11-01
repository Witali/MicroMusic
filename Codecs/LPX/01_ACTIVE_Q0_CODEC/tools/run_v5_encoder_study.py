"""Run frozen v5 encoder variants at actual 100/95/90 complete-chain caps.

This is an explicit research command. Media, paths, per-recording hashes and
candidate receipts are written only under this checkout's ignored build/.
No firmware or audibility claim is inferred from the encoder measurements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np
import soundfile as sf

from batch_decoder import BatchSession, ROOT
from benchmark_speech_flash import source_hashes
from measure_speech_firmware import checked_output
from output_paths import protect_outputs
from refine_speech_compact import quality
from refine_speech_lpc import refine as legacy_refine
from refine_speech_trajectory import refine as path_refine
from select_speech_budget import quality_source_fingerprint
from speech_chain_frontier import assemble
import speech_compact as compact
from speech_objective import SpeechObjective
from speech_rate_allocation import bit_accounting, fit_capacity
from standard_metrics import pwm_duties


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def save(path, value):
    checked_output(path)
    if path.is_symlink() or path.exists() and path.stat().st_nlink > 1:
        raise ValueError('Output receipt must not be an alias')
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def encoder_sources():
    return {p.name: sha(p.read_bytes()) for p in sorted((ROOT / 'tools').glob('*.py'))}


def legacy_seed(blob, cap):
    """Preserved amplitude control; no feasibility is inferred from capacity0."""
    fields = compact.unpack(blob)
    n, profile, spectra, _, _, _, _, extras = fields
    if len(blob) <= cap:
        return blob
    layout = bit_accounting(spectra, profile, extras)
    reclaimed, _, size, _ = fit_capacity(layout['spectrum_bits'], len(spectra), profile,
        np.asarray(extras, np.int64), cap, 0, n)
    candidate = compact.pack(*fields[:7], extras=reclaimed.tolist())[0]
    if len(candidate) != size:
        raise AssertionError('Legacy capacity differs from actual serialization')
    return candidate if len(candidate) <= cap else None


def run(manifest_path, output, *, variant='path-amplitude', mode='sse', split='tuning',
        offset=0, limit=0, frames=2, evaluations=128, beam_width=2):
    begun = time.perf_counter(); cpu = time.process_time()
    manifest_path = Path(manifest_path).resolve(); output = checked_output(output)
    receipt = output / 'results-private.json'
    if output.exists():
        raise ValueError('Use a new immutable experiment output directory')
    protect_outputs([manifest_path, Path(__file__)], [receipt])
    raw = manifest_path.read_bytes(); manifest = json.loads(raw)
    if manifest['schema'] != 'lpx-v5-encoder-quality-study-v1':
        raise ValueError('Expected frozen baseline study')
    sources = source_hashes(ROOT / 'src'); tools = encoder_sources(); metric_source = quality_source_fingerprint()
    if manifest['source_sha256'] != sources or manifest['quality_source_fingerprint'] != metric_source:
        raise ValueError('Frozen baseline decoder/metric source differs')
    if variant not in ('old-default', 'old-expanded', 'path-amplitude', 'path-marginal'):
        raise ValueError('Unknown study variant')
    if mode not in ('sse', 'perceptual') or variant.startswith('old-') and mode != 'sse':
        raise ValueError('Old search is an unchanged SSE control')
    if split not in ('tuning', 'evaluation', 'additional') or offset < 0 or limit < 0:
        raise ValueError('Invalid study cohort slice')
    records = [r for r in manifest['records'] if r['split'] == split][offset:]
    if limit:
        records = records[:limit]
    if not records:
        raise ValueError('No records in cohort slice')
    output.mkdir(parents=True)
    config = dict(variant=variant, mode=mode, split=split, offset=offset, limit=limit,
                  frames=frames, evaluations=evaluations, beam_width=beam_width)
    result = {'schema': 'lpx-v5-encoder-quality-run-v1', 'status': 'running',
        'manifest_sha256': sha(raw), 'source_sha256': sources, 'encoder_source_sha256': tools,
        'quality_source_fingerprint': metric_source, 'settings': config, 'records': []}
    guards = {str(manifest_path): sha(raw)}
    save(receipt, result)
    with BatchSession('batch', speech=True, speech_compact=True) as common, \
         BatchSession('batch', speech=True, speech_compact=True, compact_only=True) as decoder:
        verified = set()
        def verify(blob):
            digest = sha(blob)
            if digest in verified:
                return
            n = compact.unpack(blob)[0]; pcm = compact.decode_model(blob); pwm = pwm_duties(pcm)
            for native in (common, decoder):
                if not np.array_equal(native.decode_one_s16(blob, n), pcm) or not np.array_equal(native.decode_one(blob, n), pwm):
                    raise AssertionError('Whole-study common/v5/model PCM/PWM mismatch')
            verified.add(digest)
        for ordinal, record in enumerate(records, 1):
            case_start = time.perf_counter(); case_cpu = time.process_time()
            if not re.fullmatch(r'speech-profile-\d{3}', record['id']):
                raise ValueError('Invalid anonymous record identifier')
            refpath = Path(record['reference']['path']); refbytes = refpath.read_bytes()
            if sha(refbytes) != record['reference']['file_sha256']:
                raise ValueError('Original reference file changed')
            guards[str(refpath)] = sha(refbytes)
            reference, rate = sf.read(refpath, dtype='int16')
            if rate != 8000 or reference.ndim != 1 or len(reference) != record['samples'] or sha(reference.astype('<i2').tobytes()) != record['reference']['pcm16_sha256']:
                raise ValueError('Original reference PCM changed')
            baseline = []; position = 0
            for index, segment in enumerate(record['segments']):
                path = Path(segment['path']); blob = path.read_bytes(); n, p, *_ = compact.unpack(blob)
                if sha(blob) != segment['stream_sha256'] or len(blob) != segment['file_bytes'] or segment['index'] != index or segment['start'] != position or n != segment['samples'] or p != record['profile']:
                    raise ValueError('Frozen ordered stream segment changed')
                guards[str(path)] = sha(blob); baseline.append(blob); position += n; verify(blob)
            baseline_pcm = np.concatenate([compact.decode_model(b) for b in baseline])
            if position != len(reference) or sum(map(len, baseline)) != record['baseline_bytes'] or quality(reference, baseline_pcm) != record['baseline_metrics']:
                raise ValueError('Frozen complete reference/stream baseline changed')
            objective = SpeechObjective.from_chain(reference, baseline, mode=mode)
            pools = [{b} for b in baseline]; reports = []; position = 0
            for index, seed in enumerate(baseline):
                n = compact.unpack(seed)[0]; section = reference[position:position + n]
                def context(pcm, start=position, stop=position + n):
                    joined = baseline_pcm.copy(); joined[start:stop] = pcm
                    return objective(joined)
                # Pool generation uses multiple caps; final selection below uses
                # the true complete-chain cap without proportional constraints.
                caps = sorted({max(22, len(seed) * percent // 100) for percent in (100, 95, 90)}, reverse=True)
                for cap in caps:
                    candidates = []; start_cpu = time.process_time(); start_wall = time.perf_counter()
                    if variant.startswith('old-'):
                        initial = legacy_seed(seed, cap)
                        if initial is None:
                            reports.append({'segment': index, 'generation_cap': cap, 'status': 'amplitude_seed_did_not_fit'})
                            continue
                        options = {} if variant == 'old-default' else dict(frame_limit=64, spectral_candidates=4, lookahead=1280, excitation_horizon=160, passes=2)
                        selected, _, report, raw_candidate = legacy_refine(section, initial, decoder, cap, **options)
                        candidates = [initial, selected, raw_candidate]
                    else:
                        frontier = []
                        selected, _, report, raw_candidate = path_refine(section, seed, decoder, cap,
                            frame_limit=frames, window_frames=2, beam_width=beam_width,
                            spectral_candidates=2, excitation_candidates=1, excitation_horizon=80,
                            max_evaluations=evaluations, objective=context, objective_name=objective.name,
                            selection='objective', capacity_policy='marginal' if variant == 'path-marginal' else 'amplitude',
                            allocation_evaluations=min(4096, evaluations), frontier=frontier)
                        candidates = [selected, raw_candidate, *(p['stream'] for p in frontier)]
                    for candidate in candidates:
                        if candidate is not None:
                            if len(candidate) > cap:
                                raise AssertionError('Search returned a stream above its generation cap')
                            verify(candidate); pools[index].add(candidate)
                    reports.append({'segment': index, 'generation_cap': cap, 'report': report,
                                    'wall_seconds': time.perf_counter() - start_wall, 'cpu_seconds': time.process_time() - start_cpu})
                position += n
            folder = output / record['id']; folder.mkdir()
            budgets = []
            for budget in record['budgets']:
                percent = budget['percent']; cap = record['baseline_bytes'] * percent // 100
                if cap != budget['max_complete_stream_bytes']:
                    raise ValueError('Complete-chain budget changed')
                chosen = assemble(reference, baseline, pools, cap, objective=objective, beam_width=32, max_evaluations=4096)
                entries = {}
                for label, candidate in (('selected', chosen.selected), ('tradeoff', chosen.tradeoff)):
                    if candidate is None:
                        entries[label] = None
                        continue
                    segments = []
                    for index, blob in enumerate(candidate.streams):
                        verify(blob); path = folder / f'{percent}-{label}-{index}.l4hy'; path.write_bytes(blob)
                        segments.append({'path': str(path), 'stream_sha256': sha(blob), 'file_bytes': len(blob)})
                    entries[label] = {'segments': segments, 'stream_bytes': candidate.file_bytes,
                        'objective': candidate.objective, 'metrics': candidate.metrics,
                        'conservative_floors_passed': candidate.conservative_floors_passed}
                budgets.append({'percent': percent, 'cap': cap, 'selection': chosen.report, **entries})
            result['records'].append({'id': record['id'], 'profile': record['profile'], 'split': split,
                'baseline_bytes': record['baseline_bytes'], 'samples': len(reference), 'objective': objective.describe(),
                'segment_pool_sizes': [len(p) for p in pools], 'searches': reports, 'budgets': budgets,
                'wall_seconds': time.perf_counter() - case_start, 'cpu_seconds': time.process_time() - case_cpu})
            save(receipt, result)
            print(json.dumps({'phase': 'encoder-study', 'variant': variant, 'mode': mode,
                'completed': ordinal, 'total': len(records), 'seconds': time.perf_counter() - case_start}), flush=True)
        result['unique_streams_native_model_pwm_exact'] = len(verified)
    if source_hashes(ROOT / 'src') != sources or encoder_sources() != tools or quality_source_fingerprint() != metric_source:
        raise ValueError('Sources changed during the experiment')
    for path, digest in guards.items():
        if sha(Path(path).read_bytes()) != digest:
            raise ValueError('Frozen study input changed during the experiment')
    result.update(status='complete', wall_seconds=time.perf_counter() - begun, cpu_seconds=time.process_time() - cpu)
    save(receipt, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--variant', choices=('old-default', 'old-expanded', 'path-amplitude', 'path-marginal'), default='path-amplitude')
    parser.add_argument('--objective', choices=('sse', 'perceptual'), default='sse')
    parser.add_argument('--split', choices=('tuning', 'evaluation', 'additional'), default='tuning')
    parser.add_argument('--offset', type=int, default=0); parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--frames', type=int, default=2); parser.add_argument('--evaluations', type=int, default=128)
    parser.add_argument('--beam-width', type=int, default=2)
    args = parser.parse_args()
    run(args.manifest, args.output, variant=args.variant, mode=args.objective, split=args.split,
        offset=args.offset, limit=args.limit, frames=args.frames, evaluations=args.evaluations, beam_width=args.beam_width)
