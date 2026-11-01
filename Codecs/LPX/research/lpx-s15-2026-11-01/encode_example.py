"""One bounded9-candidate S15 example; no initial LPC fit or time stretching."""
import argparse
from pathlib import Path
import hashlib
import json
import time
import numpy as np
import soundfile as sf
from s15_format import ACTIVE, pack, expand, decode_model
from s15_native import build, Native
from s15_search import search
from test_s15 import contracts
import speech_compact as v5
from q0_model import coefficient_trace, table
from wav_lpc import pack_frames
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_snapshot():
    here = Path(__file__).resolve().parent
    files = sorted(here.glob('*.py')) + sorted(here.glob('*.cpp'))
    files += sorted((ACTIVE/'src').glob('*'))
    files += [ACTIVE/'tools'/name for name in ('speech_compact.py', 'speech_v4.py',
              'q0_model.py', 'wav_lpc.py', 'lpx4.py', 'standard_metrics.py',
              'rice_v3.py', 'rice_v7.py', 'batch_decoder.py')]
    return {str(p.resolve()): sha(p) for p in files if p.is_file()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path)
    ap.add_argument('seed', type=Path)
    ap.add_argument('output', type=Path)
    ap.add_argument('--compiler', required=True)
    a = ap.parse_args()
    if a.output.exists():
        raise ValueError('Fresh output directory required; preserve every attempt')
    a.output.mkdir(parents=True)
    source = source_snapshot()
    inputs = {str(p.resolve()): sha(p) for p in (a.input, a.seed)}
    started, cpu_started = time.perf_counter(), time.process_time()
    ref, rate = sf.read(a.input, dtype='int16')
    seed = v5.unpack(a.seed.read_bytes())
    n, profile, seed_spectra, seed_params, _, seed_pre, _, _ = seed
    if rate != 8000 or ref.ndim != 1 or len(ref) != n or n != 19200 or profile != 4:
        raise ValueError('This pilot requires the full19200-sample8kHz P4 seed context')
    binding = dict(schema='lpx-s15-example-private-v1', status='started', sources=source,
                   inputs=inputs, rate=rate, samples=n, original_level_gain=1,
                   cap_bytes=450, cadences=[4, 5, 6], pres=[seed_pre, 8192, 11469],
                   seed_pitch_only=True, bright=0, candidates=9)
    (a.output/'binding-private.json').write_text(json.dumps(binding, indent=2)+'\n')
    libraries = [a.output/name for name in ('common.so', 'v5-only.so')]
    recipes = [build(lib, a.compiler, compact) for lib, compact in zip(libraries, (False, True))]
    natives = [Native(lib) for lib in libraries]
    contract = contracts(*natives)
    (a.output/'contracts-private.json').write_text(json.dumps(contract, indent=2)+'\n')
    print(json.dumps(dict(stage='contracts', **contract)), flush=True)
    seed_params = np.asarray(seed_params, np.int64)
    rows = []
    best = None
    for cadence in (4, 5, 6):
        # Frozen deterministic projection of each original P4 LSF center to
        # its lower adjacent P6 center; no fitted or learned codebook.
        spectra = [[2*int(v) for v in seed_spectra[(fi//cadence)*cadence]]
                   for fi in range(len(seed_spectra))]
        vectors = [[(v<<4)+8 for v in vec] for vec in spectra for _ in range(2)]
        co = coefficient_trace(pack_frames(vectors), n)
        for pre in (seed_pre, 8192, 11469):
            index = len(rows)
            begin, cpu = time.perf_counter(), time.process_time()
            params, pulses, pcm, frames, evaluations = search(ref.astype(np.int64), co,
                table('scale_table.inc'), seed_params, pre, 0)
            blob, accounting = pack(n, spectra, params.tolist(), pulses.tolist(), pre, 0)
            assert np.array_equal(pcm, decode_model(blob))
            # Complete points become durable before any subsequent candidate.
            (a.output/f'candidate-{index:02d}.lpx').write_bytes(blob)
            error = pcm.astype(np.int64)-ref.astype(np.int64)
            score = int(np.dot(error, error))
            row = dict(id=index, cadence_frames=cadence, pre_q14=int(pre),
                       score_full_pcm_sse=score, fits_450=len(blob)<=450,
                       frame_parameter_evaluations=int(frames),
                       pulse_position_sign_evaluations=int(evaluations),
                       committed80_sample_renders=int(frames*4+60*4),
                       search_and_model_wall_seconds=time.perf_counter()-begin,
                       search_and_model_cpu_seconds=time.process_time()-cpu, **accounting)
            rows.append(row)
            (a.output/'candidates-private.json').write_text(json.dumps(rows, indent=2)+'\n')
            if row['fits_450'] and (best is None or (score, len(blob), index) < best[0]):
                best = ((score, len(blob), index), blob, pcm.copy())
            print(json.dumps(dict(stage='candidate-complete', **row)), flush=True)
    if best is None:
        raise RuntimeError('No predeclared candidate fits450B; preserve negative result')
    rank, blob, pcm = best
    expanded = expand(blob)
    for native in natives:
        assert native.expand(blob) == expanded
        assert np.array_equal(native.decode(blob, n), pcm)
        assert np.array_equal(native.decode(blob, n, True), pwm_duties(pcm))
        assert native.decoder.decode_one_s16(blob, n) is None
    pwm = pwm_pcm16(pcm).astype(np.int16)
    (a.output/'low15.lpx').write_bytes(blob)
    (a.output/'reference-expanded-v5.lpx').write_bytes(expanded)
    sf.write(a.output/'low15.wav', pwm, 8000, subtype='PCM_16')
    sf.write(a.output/'low15-pcm16.wav', pcm, 8000, subtype='PCM_16')
    reopened, rr = sf.read(a.output/'low15.wav', dtype='int16')
    assert rr == 8000 and np.array_equal(reopened, pwm) and len(reopened) == 19200
    assert source_snapshot() == source and all(sha(Path(p)) == h for p, h in inputs.items())
    chosen = rows[rank[2]]
    proof = dict(schema='lpx-s15-example-proof-v1', status='PASS', selected_id=rank[2],
                 codec='LPX-S15 experimental', container_version=8, mode=15,
                 rate_hz=8000, samples=n, duration_seconds=n/8000,
                 original_level_gain=1, synthesis_shift_samples=0,
                 resampled=False, time_stretched=False, transposed=False,
                 complete_file_bytes=len(blob), complete_file_bitrate_bps=len(blob)*8/(n/8000),
                 cap_bytes=450, selection='minimum full PCM SSE among9 fitting candidates',
                 selected=chosen, candidates=9,
                 frame_parameter_evaluations=sum(r['frame_parameter_evaluations'] for r in rows),
                 pulse_position_sign_evaluations=sum(r['pulse_position_sign_evaluations'] for r in rows),
                 pulse_selected_replays=sum(r['committed80_sample_renders'] for r in rows),
                 native_expansion_byte_exact=True, common_native_pcm_pwm_exact=True,
                 v5_only_native_pcm_pwm_exact=True, production_v5_rejects_version8=True,
                 model_pcm_exact=True, wav_pwm_native_exact=True,
                 pcm_metrics=error_metrics(ref, pcm, True), pwm_metrics=error_metrics(ref, pwm, True),
                 no_target_firmware_or_timing_admission=True,
                 work_wall_seconds=time.perf_counter()-started, process_cpu_seconds=time.process_time()-cpu_started,
                 compiler_recipes=recipes, library_sha256={lib.name:sha(lib) for lib in libraries},
                 output_sha256={name:sha(a.output/name) for name in ('low15.lpx', 'low15.wav', 'low15-pcm16.wav')})
    (a.output/'proof-private.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ('status', 'selected_id', 'complete_file_bytes',
                     'complete_file_bitrate_bps', 'samples', 'duration_seconds', 'process_cpu_seconds')}), flush=True)


if __name__ == '__main__':
    main()
