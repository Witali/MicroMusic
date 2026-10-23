"""Bounded raw-output SNR/size study of adaptive LPV1 versus fixed LPX3/LPX4."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from pystoi import stoi
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from lpc2_excitation import Lpc2Bridge, encode_excitation, decode_excitation
from lpc_vbr import encode, decode
from hq4_speech_search import deterministic_estoi
from spectrogram_objective import SpectrogramObjective


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')


def run_one(reference_path, output, *, recording_id='reference', base_path=None, targets=(20.,24.,28.),
            fixed=(2,3,4,6,8), fixed_root=None, block_samples=75):
    started = time.perf_counter()
    reference_path, output = Path(reference_path), Path(output)
    reference, sr = sf.read(reference_path, dtype='float64')
    if reference.ndim != 1 or len(reference) < 3072 or not np.all(np.isfinite(reference)):
        raise ValueError('Expected a complete finite mono reference, at least3072 samples')
    output.mkdir(parents=True, exist_ok=True)
    bridge = Lpc2Bridge(output/'encode-cache')
    if base_path is None:
        base, _ = bridge.encode(reference, sr, output/'native')
    else:
        base = Path(base_path).read_bytes()
    (output/'base.lp2').write_bytes(base)
    spectral = SpectrogramObjective(reference, sr)
    independent = Lpc2Bridge(output/'parameter-only-decode')
    base_cache = independent(base)
    if base_cache[1] != sr or len(base_cache[2]) != len(reference):
        raise ValueError('Existing base does not preserve the reference rate/count')

    def measure(audio):
        # Measure the actual FLOAT WAV values provided for listening, without
        # peak adjustment; preserve overshoot above1 if it exists.
        audio = np.asarray(audio, dtype=np.float32).astype(np.float64)
        error = float(np.mean((audio-reference)**2))
        return dict(stoi=float(stoi(reference, audio, sr)), estoi=deterministic_estoi(reference, audio, sr),
            **spectral.evaluate(audio), raw_snr_db=float(10*np.log10(max(np.mean(reference**2),1e-30)/max(error,1e-30))),
            raw_mse=error, raw_peak=float(abs(audio).max()), raw_mean=float(audio.mean()),
            raw_rms=float(np.sqrt(np.mean(audio**2))),
            samples_outside_unit_interval=int(np.count_nonzero(abs(audio) > 1)),
            float32_pcm_sha256=hashlib.sha256(np.asarray(audio, dtype='<f4').tobytes()).hexdigest())

    report = dict(schema='lpc-vbr-probe-v1', recording_id=recording_id, reference_sha256=digest(reference_path),
        sample_rate=sr, samples=len(reference), base_sha256=hashlib.sha256(base).hexdigest(),
        input_policy='Unchanged full-duration mono reference, no gain/DC/resampling/cropping changes',
        size_policy='Complete actual encoded containers: header+embeddedLPC2+blockdescriptors+codes+padding; decoder code excluded',
        output_policy='LPV1: no output clipping or normalization. Fixed controls use the original LPX3/LPX4 output clamp, explicitly retained.',
        avr_implemented=False, hardware_tested=False, profiles={})
    for width in fixed:
        name = f'lpx{3 if width <= 4 else 4}-{width}bit'
        suffix = '.lpx3' if width <= 4 else '.lpx4'
        existing = Path(fixed_root)/(name+suffix) if fixed_root else None
        if existing and existing.is_file():
            blob = existing.read_bytes()
            audio, info = decode_excitation(blob, independent)
            if info['base_sha256'] != report['base_sha256']:
                raise ValueError('Fixed comparison uses a different LPC2 base')
        else:
            blob, audio, info = encode_excitation(reference, sr, base, width, bridge, block_samples=block_samples)
        path = output/(name+suffix)
        path.write_bytes(blob)
        sf.write(output/(name+'.wav'), audio, sr, subtype='FLOAT')
        report['profiles'][name] = dict(container=path.name, container_bytes=len(blob),
            bits_per_second=len(blob)*8*sr/len(reference), container_sha256=digest(path),
            metrics=measure(audio), container_info=info, output_clipping=True)
        print(json.dumps(dict(recording=recording_id, profile=name, bytes=len(blob),
            **{k:report['profiles'][name]['metrics'][k] for k in ('raw_snr_db','stoi')})), flush=True)
    for target in targets:
        before = time.perf_counter()
        name = 'lpv1-'+format(target, 'g')+'db'
        blob, training_audio, info = encode(reference, sr, base, bridge,
            target_snr_db=target, block_samples=block_samples)
        # This bridge derives coefficients from base bytes alone in a separate
        # native decoder process. Encoding state and reference PCM are absent.
        audio, checked = decode(blob, independent)
        if not np.array_equal(training_audio, audio):
            raise AssertionError('Independent base-only decoding changed LPV1 output')
        path = output/(name+'.lpv1')
        path.write_bytes(blob)
        sf.write(output/(name+'.wav'), audio, sr, subtype='FLOAT')
        save(output/(name+'-decisions.json'), info['block_decisions'])
        del info['block_decisions']
        report['profiles'][name] = dict(container=path.name, container_bytes=len(blob),
            bits_per_second=len(blob)*8*sr/len(reference), container_sha256=digest(path),
            metrics=measure(audio), container_info=checked, training=info,
            independent_base_only_decode_exact=True, elapsed_seconds=round(time.perf_counter()-before,6),
            output_clipping=False)
        print(json.dumps(dict(recording=recording_id, profile=name, bytes=len(blob),
            failed_blocks=info['target_failed_blocks'], widths=info['width_block_counts'],
            **{k:report['profiles'][name]['metrics'][k] for k in ('raw_snr_db','stoi')})), flush=True)
    source_paths = [Path(__file__), CODEC/'lpc_vbr.py', CODEC/'lpc2_excitation.py',
        ROOT/'tools/lpc2-reference-cli.mjs', ROOT/'ATmega328/Sound/reference/lpx3/hybrid_codec.py']
    report['source_sha256_normalized_lf'] = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in source_paths}
    report['elapsed_seconds'] = round(time.perf_counter()-started,6)
    save(output/'report.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--base', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--recording-id', default='reference')
    p.add_argument('--targets', type=float, nargs='+', default=(20.,24.,28.))
    p.add_argument('--fixed', type=int, nargs='*', default=(2,3,4,6,8))
    p.add_argument('--fixed-root', type=Path)
    p.add_argument('--block-samples', type=int, default=75)
    a = p.parse_args()
    run_one(a.reference, a.output, recording_id=a.recording_id, base_path=a.base,
        targets=a.targets, fixed=a.fixed, fixed_root=a.fixed_root, block_samples=a.block_samples)


if __name__ == '__main__':
    main()
