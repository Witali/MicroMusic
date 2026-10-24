#!/usr/bin/env python3
"""Audit retained speech models, compact data, 8-bit output and listening plots."""
import argparse
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
from colored_period import decode_colored, pack_colored
from compact_period import pack_compact, unpack_compact
from period_residual import decode_residual
from hq4_core import unpack_stream
from hq4_timbre import decode as decode_timbre
from model import decode as decode_hq4
from refine_period_helpers import digest, atomic_json, matched_audio


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--models', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--plot', action='store_true')
    a = p.parse_args()
    manifest_path = ROOT / 'ATtiny13A/Sound/audio-references.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    reports = []
    for clip in manifest['clips']:
        original = a.references / clip['id'] / 'original.wav'
        if digest(original.read_bytes()) != clip['sha256']:
            raise ValueError('Reference hash mismatch')
        reference, sr = sf.read(original)
        objective = SpectralObjective(reference, sr)
        model_path = a.models / clip['id'] / 'model.json'
        model = json.loads(model_path.read_text(encoding='utf-8'))
        full = decode_colored(model)
        compact = pack_compact(model)
        exact = decode_colored(unpack_compact(compact))
        if not np.array_equal(full, exact):
            raise AssertionError('Compact format changes decoded PCM')
        rounded = np.rint(full*128).clip(-128, 127)/128
        if clip['id'] == 'chego':
            stream_path = CODEC / 'timbre/chego-auto/speech.hq'
            control_name, decoder, decoder_bytes = 'HQ4-T Auto', decode_timbre, 422
        else:
            stream_path = CODEC / 'release' / clip['id'] / 'speech.hq'
            control_name, decoder, decoder_bytes = 'HQ4', decode_hq4, 406
        frames, durations = unpack_stream(stream_path.read_bytes())
        control = (decoder(frames, durations).astype(float)-128)/128
        previous_path = ROOT / 'ATtiny13A/Sound/research/period-wave' / clip['id'] / 'residual-model.json'
        previous = decode_residual(json.loads(previous_path.read_text(encoding='utf-8')))
        clips = dict(Original=reference, Control=control, Before=previous, NewFloat=full, New8bit=rounded)
        if any(len(x) != len(reference) for x in clips.values()):
            raise ValueError('Duration mismatch')
        report = dict(clip_id=clip['id'], title=clip['title'], reference_sha256=clip['sha256'],
                      model_sha256=digest(model_path.read_bytes()), previous_model_sha256=digest(previous_path.read_bytes()),
                      control_name=control_name, control_stream_sha256=digest(stream_path.read_bytes()),
                      control_assembled_flash_bytes=decoder_bytes+len(stream_path.read_bytes())+1,
                      native_data_bytes=len(pack_colored(model)), compact_data_bytes=len(compact),
                      compact_payload_sha256=digest(compact), available_flash_after_compact_data=1024-len(compact),
                      compact_pcm_exact=True, output_rounding='round(x*128), clip [-128,127], divide by 128',
                      avr_assembled=False, hardware_verified=False, metrics={})
        for name in ('Control', 'Before', 'NewFloat', 'New8bit'):
            x = clips[name]
            report['metrics'][name] = dict(**objective.spectrum(x), stoi=float(stoi(reference, x, sr)),
                                          estoi=float(stoi(reference, x, sr, extended=True)),
                                          peak=float(np.max(abs(x))))
        output = a.output / clip['id']
        output.mkdir(parents=True, exist_ok=True)
        (output / 'speech.px').write_bytes(compact)
        atomic_json(output / 'quality.json', report)
        matched_audio(output, clips, objective, ('Original', 'Control', 'Original', 'New8bit'))
        if a.plot:
            os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'build/matplotlib-config'))
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            balanced = {}
            for name in ('Original', 'Control', 'New8bit'):
                x = sosfilt(objective.hp, clips[name])
                balanced[name] = x*objective.rms/(np.sqrt(np.mean(x*x))+1e-12)
            peak = np.max(abs(stft(balanced['Original'], nperseg=256, noverlap=192)[2]))
            fig, axes = plt.subplots(3, 1, figsize=(11, 8.3), sharex=True, sharey=True, layout='constrained')
            for ax, name in zip(axes, ('Original', 'Control', 'New8bit')):
                f, t, spectrum = stft(balanced[name], fs=sr, nperseg=256, noverlap=192)
                db = 20*np.log10(np.maximum(abs(spectrum)/peak, 1e-4))
                artist = ax.pcolormesh(t, f, db, shading='auto', cmap='magma', vmin=-65, vmax=0)
                title = 'Оригинал' if name == 'Original' else control_name if name == 'Control' else 'Новый прототип, округление выхода до 8 бит'
                if name != 'Original':
                    q = report['metrics'][name]
                    title += f"\nSTOI {q['stoi']:.4f} | eSTOI {q['estoi']:.4f} | log {q['log_spectral_error']:.4f}"
                ax.set_title(title, loc='left', fontsize=10); ax.set_ylabel('Гц')
                ax.set_ylim(0, sr/2); ax.set_xlim(0, len(reference)/sr)
            axes[-1].set_xlabel('Время, с')
            fig.colorbar(artist, ax=axes, label='дБ, общий уровень и цветовая шкала', shrink=.85)
            fig.suptitle(f"{clip['title']}\n{len(compact)} байт данных; AVR-декодер ещё не собран", fontsize=12)
            fig.savefig(output / 'spectrograms.png', dpi=140)
            plt.close(fig)
        reports.append(report)
        print(json.dumps(dict(clip=clip['id'], compact_bytes=len(compact), metrics=report['metrics'])), flush=True)
    sources = [CODEC / name for name in ('compact_period.py', 'colored_period.py', 'period_wave.py', 'period_residual.py', 'auto_encoder.py', 'hq4_core.py', 'hq4_timbre.py', 'model.py')]
    sources += [Path(__file__), ROOT / 'tools/refine_period_helpers.py']
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'numba', 'pystoi', 'soundfile')}
    runtime['python'] = sys.version.split()[0]
    atomic_json(a.output / 'quality.json', dict(schema='speech-quality-review-v1', sources_sha256_normalized_lf=fingerprints,
                manifest_sha256=digest(manifest_path.read_bytes()), runtime=runtime, clips=reports))


if __name__ == '__main__':
    main()
