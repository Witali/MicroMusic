#!/usr/bin/env python3
"""Independently validate tiny speech quality, packed PCM and listening files."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

import numpy as np
from pystoi import stoi
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from fixed_period import decode_fixed
from hq4_core import unpack_stream
from hq4_timbre import decode as decode_timbre
from tiny_period import pack_tiny, unpack_tiny
from refine_period_helpers import atomic_json, digest, matched_audio


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest_path = ROOT/'ATtiny13A/Sound/audio-references.json'
    clip = next(c for c in json.loads(manifest_path.read_text(encoding='utf-8'))['clips'] if c['id']=='chego')
    if digest(args.reference.read_bytes()) != clip['sha256']:
        raise ValueError('Reference SHA-256 does not match canonical chego')
    reference, sr = sf.read(args.reference)
    objective = SpectralObjective(reference, sr)
    model = json.loads(args.model.read_text(encoding='utf-8'))
    pcm = decode_fixed(model)
    packed = pack_tiny(model)
    restored = unpack_tiny(packed)
    if not np.array_equal(pcm, decode_fixed(restored)):
        raise AssertionError('Tiny Flash/EEPROM packing changes exact integer PCM')
    if len(pcm) != len(reference):
        raise ValueError('Reference/model duration mismatch')
    control_path = CODEC/'timbre/chego-auto/speech.hq'
    frames, durations = unpack_stream(control_path.read_bytes())
    previous_path = ROOT/'ATtiny13A/Sound/research/fixed-period/chego/white-model.json'
    previous = json.loads(previous_path.read_text(encoding='utf-8'))
    clips = dict(Original=reference,
                 HQ4TAuto=(decode_timbre(frames, durations).astype(float)-128)/128,
                 Fixed16=(decode_fixed(previous).astype(float)-128)/128,
                 Tiny=(pcm.astype(float)-128)/128)
    metrics = {}
    for name, audio in clips.items():
        signed = audio*128
        metrics[name] = dict(**objective.spectrum(audio),
                             stoi=float(stoi(reference, audio, sr)),
                             estoi=float(stoi(reference, audio, sr, extended=True)),
                             peak=float(np.max(abs(audio))), mean_pcm=float(np.mean(signed)),
                             max_abs_64_sample_mean=float(max(abs(np.mean(signed[i:i+64]))
                                                              for i in range(0, len(signed), 64))))
    raw_pcm = decode_fixed(dict(model, dc_block_shift=0))
    source_paths = [Path(__file__), ROOT/'tools/train-tiny-speech.py', ROOT/'tools/refine_period_helpers.py']
    source_paths += [CODEC/name for name in ('fixed_period.py', 'fixed_search.py', 'dc_blocker.py',
                                            'tiny_period.py', 'compact_period.py', 'colored_period.py',
                                            'period_wave.py', 'auto_encoder.py', 'hq4_core.py', 'hq4_timbre.py')]
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):
                    digest(path.read_text(encoding='utf-8').encode()) for path in source_paths}
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile', 'numba')}
    runtime['python'] = sys.version.split()[0]
    report = dict(schema='tiny-speech-quality-review-v1', clip_id='chego',
                  reference_sha256=clip['sha256'], manifest_sha256=digest(manifest_path.read_bytes()),
                  model_sha256=digest(args.model.read_bytes()), previous_model_sha256=digest(previous_path.read_bytes()),
                  control_stream_sha256=digest(control_path.read_bytes()),
                  pcm_sha256=digest(pcm.tobytes()), raw_pcm_sha256=digest(raw_pcm.tobytes()),
                  source_sha256_normalized_lf=fingerprints, runtime=runtime, metrics=metrics,
                  phrase_samples=len(pcm), sample_rate=sr, duration_seconds=len(pcm)/sr,
                  output_clips=int(np.sum((pcm==0)|(pcm==255))),
                  pre_dc_clips=int(np.sum((raw_pcm==0)|(raw_pcm==255))),
                  raw_mean_pcm=float(np.mean(raw_pcm.astype(float)-128)),
                  flash_data_bytes=len(packed['flash_data']), waveform_flash_bytes=len(packed['flash_tables']),
                  parameter_stream_bytes=len(packed['field_stream']),
                  eeprom_used_bytes=packed['constants']['EEPROM_USED_BYTES'],
                  packed_pcm_exact=True, compile_constants=packed['constants'],
                  hardware_verified=False,
                  assembly_verification='A separate build report must establish code size, cycle deadlines and SRAM.')
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output/'quality.json', report)
    (args.output/'expected.raw').write_bytes(pcm.tobytes())
    # Preserve the 8-bit samples; these files contain no automatic volume fit.
    sf.write(args.output/'tiny-raw-level.wav', clips['Tiny'], sr, subtype='PCM_16')
    matched_audio(args.output, clips, objective, ('Original', 'HQ4TAuto', 'Original', 'Tiny'))
    print(json.dumps(dict(metrics=metrics, flash_data_bytes=report['flash_data_bytes'],
                          eeprom_used_bytes=report['eeprom_used_bytes'],
                          clips=report['output_clips'], pcm_sha256=report['pcm_sha256']), indent=2))


if __name__ == '__main__':
    main()
