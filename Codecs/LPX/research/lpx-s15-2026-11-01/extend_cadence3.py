"""Exactly three prospective cadence3 candidates versus the closed v1 winner."""
import argparse
from pathlib import Path
import json
import time
import numpy as np
import soundfile as sf
from s15_format import pack, expand, decode_model
from s15_native import Native
from s15_search import search
from encode_example import sha, source_snapshot
import speech_compact as v5
from q0_model import coefficient_trace, table
from wav_lpc import pack_frames
from standard_metrics import error_metrics, pwm_duties, pwm_pcm16


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('incumbent', type=Path)
    ap.add_argument('output', type=Path)
    a = ap.parse_args()
    if a.output.exists():
        raise ValueError('Fresh output directory required')
    a.output.mkdir(parents=True)
    old = json.loads((a.incumbent/'binding-private.json').read_text())
    old_proof = json.loads((a.incumbent/'proof-private.json').read_text())
    assert old_proof['status'] == 'PASS' and old_proof['candidates'] == 9
    # Reopen the exact closed source/input epoch before reusing its native DLLs.
    assert all(sha(Path(p)) == h for p, h in old['sources'].items())
    assert all(sha(Path(p)) == h for p, h in old['inputs'].items())
    input_path = next(Path(p) for p in old['inputs'] if Path(p).suffix.lower() == '.wav')
    seed_path = next(Path(p) for p in old['inputs'] if Path(p).suffix.lower() == '.lpx')
    ref, rate = sf.read(input_path, dtype='int16')
    n, profile, seed_spectra, seed_params, _, seed_pre, _, _ = v5.unpack(seed_path.read_bytes())
    assert rate == 8000 and n == len(ref) == 19200 and ref.ndim == 1 and profile == 4
    libraries = [a.incumbent/name for name in ('common.so', 'v5-only.so')]
    assert all(sha(lib) == old_proof['library_sha256'][lib.name] for lib in libraries)
    natives = [Native(lib) for lib in libraries]
    incumbent = (a.incumbent/'low15.lpx').read_bytes()
    assert sha(a.incumbent/'low15.lpx') == old_proof['output_sha256']['low15.lpx']
    incumbent_pcm, rr = sf.read(a.incumbent/'low15-pcm16.wav', dtype='int16')
    assert sha(a.incumbent/'low15-pcm16.wav') == old_proof['output_sha256']['low15-pcm16.wav']
    assert rr == 8000 and len(incumbent_pcm) == n
    error = incumbent_pcm.astype(np.int64)-ref.astype(np.int64)
    incumbent_sse = int(np.dot(error, error))
    assert incumbent_sse == old_proof['selected']['score_full_pcm_sse']
    source = source_snapshot()
    pinned = {str(p.resolve()): sha(p) for p in [input_path, seed_path, *libraries,
              a.incumbent/'binding-private.json', a.incumbent/'proof-private.json',
              a.incumbent/'low15.lpx', a.incumbent/'low15-pcm16.wav']}
    binding = dict(schema='lpx-s15-cadence3-private-v1', status='started', sources=source,
                   inputs=pinned, incumbent=str(a.incumbent.resolve()),
                   preserved_incumbent_bytes=len(incumbent), preserved_incumbent_sse=incumbent_sse,
                   native_bridge='exact original libraries, binaries and all old recorded source bytes reopened',
                   cadence_frames=3, pres=[seed_pre, 8192, 11469], new_candidates=3,
                   cap_bytes=450, original_level_gain=1, rate_hz=rate, samples=n)
    (a.output/'binding-private.json').write_text(json.dumps(binding, indent=2)+'\n')
    started, cpu_started = time.perf_counter(), time.process_time()
    spectra = [[2*int(v) for v in seed_spectra[(fi//3)*3]] for fi in range(len(seed_spectra))]
    vectors = [[(v<<4)+8 for v in vec] for vec in spectra for _ in range(2)]
    co = coefficient_trace(pack_frames(vectors), n)
    seed_params = np.asarray(seed_params, np.int64)
    best = ((incumbent_sse, len(incumbent), -1), incumbent, incumbent_pcm.copy())
    rows = []
    for index, pre in enumerate((seed_pre, 8192, 11469)):
        begin, cpu = time.perf_counter(), time.process_time()
        params, pulses, pcm, frames, evaluations = search(ref.astype(np.int64), co,
            table('scale_table.inc'), seed_params, pre, 0)
        blob, accounting = pack(n, spectra, params.tolist(), pulses.tolist(), pre, 0)
        assert np.array_equal(pcm, decode_model(blob))
        (a.output/f'candidate-{index:02d}.lpx').write_bytes(blob)
        error = pcm.astype(np.int64)-ref.astype(np.int64)
        score = int(np.dot(error, error))
        row = dict(id=index, cadence_frames=3, pre_q14=int(pre), score_full_pcm_sse=score,
                   fits_450=len(blob)<=450, frame_parameter_evaluations=int(frames),
                   pulse_position_sign_evaluations=int(evaluations),
                   committed80_sample_renders=int(frames*4+60*4),
                   search_and_model_wall_seconds=time.perf_counter()-begin,
                   search_and_model_cpu_seconds=time.process_time()-cpu, **accounting)
        rows.append(row)
        (a.output/'candidates-private.json').write_text(json.dumps(rows, indent=2)+'\n')
        if row['fits_450'] and (score, len(blob), index) < best[0]:
            best = ((score, len(blob), index), blob, pcm.copy())
        print(json.dumps(dict(stage='candidate-complete', **row)), flush=True)
    rank, blob, pcm = best
    expected = decode_model(blob)
    assert np.array_equal(expected, pcm)
    expanded = expand(blob)
    for native in natives:
        assert native.expand(blob) == expanded
        assert np.array_equal(native.decode(blob, n), pcm)
        assert np.array_equal(native.decode(blob, n, True), pwm_duties(pcm))
        assert native.decoder.decode_one_s16(blob, n) is None
    pwm = pwm_pcm16(pcm).astype(np.int16)
    (a.output/'low15.lpx').write_bytes(blob)
    sf.write(a.output/'low15.wav', pwm, 8000, subtype='PCM_16')
    sf.write(a.output/'low15-pcm16.wav', pcm, 8000, subtype='PCM_16')
    reopened, rr = sf.read(a.output/'low15.wav', dtype='int16')
    assert rr == 8000 and np.array_equal(reopened, pwm) and len(reopened) == n
    assert source_snapshot() == source and all(sha(Path(p)) == h for p, h in pinned.items())
    proof = dict(schema='lpx-s15-cadence3-proof-v1', status='PASS', codec='LPX-S15 experimental',
                 container_version=8, mode=15, rate_hz=8000, samples=n, duration_seconds=n/8000,
                 original_level_gain=1, synthesis_shift_samples=0, resampled=False,
                 time_stretched=False, transposed=False, seed_pitch_only=True,
                 new_candidates=3, previously_completed_candidates=9, cumulative_candidates=12,
                 selected_origin='closed-v1-incumbent' if rank[2] == -1 else 'new-cadence3',
                 selected_id=rank[2], complete_file_bytes=len(blob),
                 complete_file_bitrate_bps=len(blob)*8/(n/8000), cap_bytes=450,
                 selected_full_pcm_sse=rank[0], incumbent_full_pcm_sse=incumbent_sse,
                 selected=old_proof['selected'] if rank[2] == -1 else rows[rank[2]],
                 selection='minimum full PCM SSE, actual bytes, ordinal among incumbent and3 fitting new candidates',
                 frame_parameter_evaluations=sum(r['frame_parameter_evaluations'] for r in rows),
                 pulse_position_sign_evaluations=sum(r['pulse_position_sign_evaluations'] for r in rows),
                 pulse_selected_replays=sum(r['committed80_sample_renders'] for r in rows),
                 cumulative_frame_parameter_evaluations=old_proof['frame_parameter_evaluations']+sum(r['frame_parameter_evaluations'] for r in rows),
                 cumulative_pulse_position_sign_evaluations=old_proof['pulse_position_sign_evaluations']+sum(r['pulse_position_sign_evaluations'] for r in rows),
                 native_expansion_byte_exact=True, common_native_pcm_pwm_exact=True,
                 v5_only_native_pcm_pwm_exact=True, production_v5_rejects_version8=True,
                 model_pcm_exact=True, wav_pwm_native_exact=True,
                 pcm_metrics=error_metrics(ref, pcm, True), pwm_metrics=error_metrics(ref, pwm, True),
                 no_target_firmware_or_timing_admission=True,
                 new_work_wall_seconds=time.perf_counter()-started,
                 new_process_cpu_seconds=time.process_time()-cpu_started,
                 previous_v1_work_wall_seconds=old_proof['work_wall_seconds'],
                 previous_v1_process_cpu_seconds=old_proof['process_cpu_seconds'],
                 output_sha256={name:sha(a.output/name) for name in ('low15.lpx', 'low15.wav', 'low15-pcm16.wav')})
    (a.output/'proof-private.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ('status', 'selected_origin', 'complete_file_bytes',
                     'complete_file_bitrate_bps', 'selected_full_pcm_sse', 'incumbent_full_pcm_sse',
                     'samples', 'duration_seconds', 'new_process_cpu_seconds')}), flush=True)


if __name__ == '__main__':
    main()
