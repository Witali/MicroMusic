#!/usr/bin/env python3
"""Reproducible three-clip period-wave experiment; original WAVs stay external."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt, stft
from pystoi import stoi

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT / 'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from hq4_core import unpack_stream
from hq4_timbre import decode as decode_timbre
from model import decode as decode_hq4
from period_wave import encode_model, decode_model, packed_bytes, unpack_bytes, refine_frames


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8', newline='\n')


def run_clip(clip, reference_root, output, starts, proposals, plot):
    path = reference_root / clip['id'] / 'original.wav'
    source = path.read_bytes()
    if sha(source) != clip['sha256']:
        raise ValueError(f"Reference hash mismatch: {path}")
    reference, sr = sf.read(path)
    if sr != clip['sample_rate'] or len(reference) != clip['samples'] or reference.ndim != 1:
        raise ValueError('Unexpected WAV format')
    objective = SpectralObjective(reference, sr)
    model, analysis = encode_model(reference, starts=starts)
    initial_audio = decode_model(model)
    model, search = refine_frames(model, objective, proposals=proposals)
    payload = packed_bytes(model)
    candidate = decode_model(unpack_bytes(payload))
    if not np.array_equal(candidate, decode_model(model)):
        raise AssertionError('Payload roundtrip changed audio')
    streams = {'HQ4': CODEC / 'release' / clip['id'] / 'speech.hq'}
    if clip['id'] == 'chego':
        streams['HQ4-T Auto'] = CODEC / 'timbre/chego-auto/speech.hq'
    clips = {'Original': reference}
    report = dict(clip_id=clip['id'], title=clip['title'], reference_sha256=sha(source),
                  samples=len(reference), sample_rate=sr, seed=23065, starts=starts,
                  avr_assembled=False, hardware_verified=False, search=search,
                  before_search=dict(**objective.spectrum(initial_audio), stoi=float(stoi(reference, initial_audio, sr))), metrics={})
    for name, path in streams.items():
        frames, durations = unpack_stream(path.read_bytes())
        decoder = decode_hq4 if name == 'HQ4' else decode_timbre
        pcm = decoder(frames, durations)
        x = (pcm.astype(float)-128)/128
        if len(x) != len(reference):
            raise ValueError(f'Duration mismatch: {name}')
        clips[name] = x
        report['metrics'][name] = dict(**objective.spectrum(x), stoi=float(stoi(reference, x, sr)),
                                      assembled_flash_bytes=(406 if name == 'HQ4' else 422)+len(path.read_bytes())+1,
                                      stream_sha256=sha(path.read_bytes()))
    clips['Period unquantized'] = analysis['continuous_unquantized']
    clips['Period 16x32'] = candidate
    for name in ('Period unquantized', 'Period 16x32'):
        x = clips[name]
        report['metrics'][name] = dict(**objective.spectrum(x), stoi=float(stoi(reference, x, sr)),
                                      waveform_snr_db=float(10*np.log10(np.sum(reference**2)/max(np.sum((reference-x)**2), 1e-20))))
    voiced = analysis['f0'] > 0
    report.update(data_bytes=len(payload), header_bytes=10, codebook_bytes=256,
                  frame_bytes=len(payload)-266, available_flash_after_data=1024-len(payload),
                  voiced_frame_fraction=float(np.mean(voiced)),
                  f0_voiced_percentiles_hz=np.percentile(analysis['f0'][voiced], [5, 50, 95]).tolist() if np.any(voiced) else [],
                  max_phase_quantization_error_cycles=float(np.max(abs(analysis['phase']-analysis['phase_target']))),
                  decoder_reference_independent=True, payload_sha256=sha(payload),
                  unquantized_model='floating per-frame periods; same quantized phase; unvoiced muted; no size claim')
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'model.json', model)
    (output / 'speech.pw').write_bytes(payload)
    write_json(output / 'analysis.json', {k: analysis[k].tolist() for k in ('centres', 'f0', 'periodicity')})
    write_json(output / 'quality.json', report)
    balanced = {}
    for name, audio in clips.items():
        y = sosfilt(objective.hp, audio)
        balanced[name] = y*objective.rms/(np.sqrt(np.mean(y*y))+1e-10)
    scale = .85/max(np.max(abs(x)) for x in balanced.values())
    for name, audio in balanced.items():
        sf.write(output / (name.lower().replace(' ', '-')+'.wav'), audio*scale, sr, subtype='PCM_16')
    order = ['Original', 'HQ4-T Auto' if 'HQ4-T Auto' in clips else 'HQ4', 'Original', 'Period 16x32']
    sequence = np.concatenate([np.r_[balanced[name]*scale, np.zeros(round(sr*.3))] for name in order])
    sf.write(output / 'comparison.wav', sequence, sr, subtype='PCM_16')
    if plot:
        os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'build/matplotlib-config'))
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(4, 1, figsize=(11, 10), layout='constrained')
        peak = np.max(abs(stft(balanced['Original'], fs=sr, nperseg=256, noverlap=192)[2]))
        for ax, name in zip(axes[:3], [order[0], order[1], order[-1]]):
            f, t, spectrum = stft(balanced[name], fs=sr, nperseg=256, noverlap=192)
            db = 20*np.log10(np.maximum(abs(spectrum)/peak, 1e-4))
            artist = ax.pcolormesh(t, f, db, shading='auto', vmin=-65, vmax=0, cmap='magma')
            ax.set_ylim(0, sr/2); ax.set_xlim(0, len(reference)/sr)
            metrics = report['metrics'].get(name)
            suffix = f" | log error {metrics['log_spectral_error']:.3f}, STOI {metrics['stoi']:.3f}" if metrics else ''
            ax.set_title(name+suffix, loc='left'); ax.set_ylabel('Hz')
        axes[3].plot(analysis['centres']/sr, np.where(voiced, analysis['f0'], np.nan), '.-', label='Original F0 estimate (not ground truth)')
        axes[3].set_xlim(0, len(reference)/sr); axes[3].set_ylim(50, 850)
        axes[3].set_ylabel('F0, Hz'); axes[3].set_xlabel('Time, seconds'); axes[3].legend()
        fig.colorbar(artist, ax=axes[:3], label='dB, shared level/color scale')
        fig.suptitle(f"{clip['title']} | PC prototype, {len(payload)} data bytes; decoder not assembled")
        fig.savefig(output / 'spectrograms.png', dpi=130)
        plt.close(fig)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True, help='External/ignored directory with <clip>/original.wav')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--starts', type=int, default=8)
    p.add_argument('--proposals', type=int, default=5000)
    p.add_argument('--plot', action='store_true')
    a = p.parse_args()
    if a.starts < 1 or a.proposals < 0:
        p.error('Starts must be positive; proposals must be nonnegative')
    manifest = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    reports = []
    for clip in manifest['clips']:
        report = run_clip(clip, a.references, a.output / clip['id'], a.starts, a.proposals, a.plot)
        reports.append(report)
        print(json.dumps(dict(clip=clip['id'], data_bytes=report['data_bytes'], metrics=report['metrics']), ensure_ascii=False), flush=True)
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'): sha(path.read_text(encoding='utf-8').encode('utf-8')) for path in
                    [CODEC / 'period_wave.py', Path(__file__), CODEC / 'auto_encoder.py', CODEC / 'hq4_timbre.py', CODEC / 'model.py', CODEC / 'hq4_core.py']}
    versions = {name: importlib.metadata.version(name) for name in ('numpy', 'scipy', 'numba', 'soundfile', 'pystoi')}
    versions['python'] = sys.version.split()[0]
    write_json(a.output / 'quality.json', dict(schema='period-wave-experiment-v2', runtime=versions,
               sources_sha256_normalized_lf=fingerprints, clips=reports))


if __name__ == '__main__':
    main()
