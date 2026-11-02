"""Three preregistered source-period proposal chains; no decoder changes.

See PITCH_PROTOCOL.md. Imports frozen helpers but never modifies their files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

for variable in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'NUMBA_NUM_THREADS'):
    os.environ[variable] = '1'

ROOT = Path(__file__).resolve().parents[4]
ACTIVE = ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
sys.path.insert(0, str(ACTIVE/'tools'))

import numpy as np
from numba import njit
import speech_compact as compact
import speech_sparse80 as sparse
from encode_low_bitrate_speech import fit_block, trial_group
from q0_model import coefficient_trace, table
from standard_metrics import pwm_pcm16
from voice_input import load_voice_wav
from wav_lpc import pack_frames
from round_admission import RoundAdmission, fields, save


def source_mask(track, block, blocks):
    """Source-only lag proposal, zero for unknown or unsupported periods."""
    result = np.zeros(blocks, np.int64)
    if not len(track.period):
        return result
    for index in range(blocks):
        center = index*block+block/2
        nearest = int(np.argmin(abs(track.sample_center-center)))
        period = track.period[nearest]
        if (track.voiced[nearest] and track.confidence[nearest] >= .85
                and abs(track.sample_center[nearest]-center) <= 160
                and np.isfinite(period)):
            integer = int(np.rint(period))
            if 18 <= integer <= 145:
                result[index] = integer
    return result


@njit(cache=True)
def constrained_chain(reference, co, seed_params, seed_pulses, lags, steps,
                       pre, sparse80, gain_floor):
    group, block = (80, 320) if sparse80 else (20, 160)
    parameters, pulses = seed_params.copy(), seed_pulses.copy()
    output = np.empty(len(reference), np.int16)
    history, ring = np.zeros(10, np.int64), np.zeros(256, np.int64)
    dd = cc = 0
    trials = selected_replays = unchanged_group_renders = 0
    for bi in range(len(parameters)):
        start = bi*block
        if lags[bi]:
            best = np.int64(9223372036854775807)
            best_scale, best_lag, best_gain = 0, lags[bi], gain_floor
            for scale in range(max(0, seed_params[bi, 0]-2), min(31, seed_params[bi, 0]+2)+1):
                for lag in range(max(18, lags[bi]-1), min(145, lags[bi]+1)+1):
                    for gain in range(gain_floor, 15, 2):
                        loss, _, _, _, _, _, _ = fit_block(reference, co, history, dd, cc,
                            ring, start, group, block, steps[scale*8], lag, gain, pre, sparse80, True)
                        trials += 1
                        if loss < best:
                            best, best_scale, best_lag, best_gain = loss, scale, lag, gain
            _, history, dd, cc, ring, pp, pcm = fit_block(reference, co, history, dd, cc,
                ring, start, group, block, steps[best_scale*8], best_lag, best_gain, pre, sparse80, True)
            selected_replays += 1
            parameters[bi] = np.asarray([best_scale, best_lag, best_gain])
            pulses[start//group:(start+block)//group] = pp
            output[start:start+block] = pcm
        else:
            scale, lag, gain = parameters[bi]
            for part in range(block//group):
                at = start+part*group
                position, amplitude = pulses[at//group]
                _, history, dd, cc, ring, pcm = trial_group(reference, co, history, dd, cc,
                    ring, at, group, steps[scale*8], lag, gain, position, amplitude, pre, False)
                unchanged_group_renders += 1
                output[at:at+group] = pcm
    return parameters, pulses, output, trials, selected_replays, unchanged_group_renders


def run(reference, incumbent, output, common, only, *, speech=True):
    started = time.perf_counter()
    admission = RoundAdmission(reference, incumbent, output, common, only, speech=speech)
    reference, output = admission.reference, admission.output
    n, sparse80, spectra, params, pulses, pre, bright = fields(incumbent)
    if len(reference) != n or bright:
        raise ValueError('Expected the exact target length and zero brightness')
    padded = np.pad(reference.astype(np.int64), (0, (-n)%320))
    shift = 4 if sparse80 else 5
    vectors = [[(int(value)<<shift)+(1<<(shift-1)) for value in vector]
               for vector in spectra for _ in range(2)]
    co = coefficient_trace(pack_frames(vectors), len(padded))
    track = admission.track
    block = 320 if sparse80 else 160
    mask = source_mask(track, block, len(params))
    settings = dict(source_period_mask=mask.tolist(), masked_blocks=int(np.count_nonzero(mask)),
        legal_gain_floors=[8, 10, 12], lag_neighbor_offsets=[-1, 0, 1], scale_neighbor_radius=2,
        maximum_parameter_trials_per_masked_block=60, input_bitrate_cap_bytes=admission.cap,
        source_voiced_windows=int(track.voiced.sum()), reference_samples=n,
        incumbent_sha256=hashlib.sha256(incumbent).hexdigest())
    save(output/'plan-private.json', settings)
    for gain_floor in (8, 10, 12):
        pp, ii, pcm, fits, replays, unchanged = constrained_chain(padded, co,
            np.asarray(params, np.int64), np.asarray(pulses, np.int64), mask,
            table('scale_table.inc'), pre, sparse80, gain_floor)
        blob = (sparse.pack(n, spectra, pp.tolist(), ii.tolist(), pre, bright) if sparse80 else
                compact.pack(n, 4, spectra, pp.tolist(), ii.tolist(), pre, bright)[0])
        admission.add(blob, pcm, origin=dict(source_pitch_gain_floor=gain_floor), work=dict(parameter_trials=int(fits),
            selected_block_replays=int(replays), unchanged_group_renders=int(unchanged),
            pulse_position_sign_trials=int((fits+replays)*(512 if sparse80 else 256))))
    return admission.finish(round='source_period_proposals', settings=settings, new_complete_contenders=3,
        source_frozen_mask=True, seconds=time.perf_counter()-started,
        scope='Finite source-period proposals; objective proxies do not prove perceptual improvement')


def main():
    from batch_decoder import BatchDecoder, build_library
    from pcm16_wav import write_pcm16_wav
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('incumbent', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--compiler', default='g++')
    parser.add_argument('--level-policy', choices=('preserve', 'auto-quiet'), default='auto-quiet')
    args = parser.parse_args()
    reference, input_info = load_voice_wav(args.reference, args.level_policy)
    libraries = []
    library_dir = args.output.with_name(args.output.name+'-native')
    library_dir.resolve().relative_to((ROOT/'build').resolve())
    library_dir.mkdir(parents=True, exist_ok=False)
    for compact_only in (False, True):
        library = library_dir/('only.so' if compact_only else 'common.so')
        build_library(library, args.compiler, speech=True, speech_compact=True, compact_only=compact_only)
        libraries.append(BatchDecoder(library))
    blob, pcm, report = run(reference, args.incumbent.read_bytes(), args.output, *libraries)
    write_pcm16_wav(args.output/'decoded.wav', pwm_pcm16(pcm))
    save(args.output/'input-private.json', input_info)
    print(json.dumps(dict(selected_id=report['selected_id'], changed=report['selected_differs_from_incumbent'],
                         seconds=report['seconds'])))


if __name__ == '__main__':
    main()
