"""Prepare arbitrary external recordings for speech trials without cutting speech.

Original media stays external. Generated references and previews belong in
ignored build/. A retained manifest can record source/reference hashes alone.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re

import numpy as np
from scipy.signal import resample_poly
import soundfile as sf


def sha(value):
    return hashlib.sha256(value).hexdigest()


def prepare(path, output, sample_rate=7500, *, start_seconds=None, end_seconds=None):
    path, output = Path(path), Path(output)
    if sample_rate != 7500:
        raise ValueError('Current firmware trials require 7500 Hz')
    source = path.read_bytes()
    audio, rate = sf.read(path, always_2d=True, dtype='float64')
    if not len(audio) or not np.all(np.isfinite(audio)):
        raise ValueError('Source is empty or contains nonfinite samples')
    total_samples = len(audio)
    start = 0 if start_seconds is None else round(start_seconds*rate)
    end = total_samples if end_seconds is None else round(end_seconds*rate)
    if not 0 <= start < end <= total_samples:
        raise ValueError('Requested source time range is empty or outside the recording')
    mono = audio[start:end].mean(axis=1)
    source_mean = float(mono.mean())
    mono -= source_mean
    common = math.gcd(int(rate), sample_rate)
    converted = resample_poly(mono, sample_rate//common, int(rate)//common)
    resampled_samples = len(converted)
    peak = float(np.max(abs(converted)))
    if peak < 1e-7:
        raise ValueError('Source recording is silent')
    gain = .85/peak
    converted *= gain
    padding = (-len(converted)) % 64
    converted = np.pad(converted, (0, padding))
    if len(converted) < 3072:
        raise ValueError('At least 3072 reference samples are needed for quality assessment')
    output.mkdir(parents=True, exist_ok=True)
    reference_path = output/'reference.wav'
    sf.write(reference_path, converted, sample_rate, subtype='PCM_16')
    reference, _ = sf.read(reference_path)
    rms = float(np.sqrt(np.mean(reference**2)))
    return dict(id=output.name, source_file=path.name, source_sha256=sha(source),
                source_bytes=len(source), source_sample_rate=int(rate),
                source_channels=audio.shape[1], source_samples=total_samples,
                source_seconds=total_samples/rate, source_mono_dc_removed=source_mean,
                selection_start_seconds=start/rate, selection_end_seconds=end/rate,
                mono_policy='arithmetic mean of channels',
                resampling='scipy.signal.resample_poly default Kaiser anti-alias filter',
                normalization_gain=gain, sample_rate=sample_rate,
                reference_samples=len(reference), unpadded_samples=resampled_samples,
                trailing_zero_padding_samples=padding, reference_seconds=len(reference)/sample_rate,
                speech_cropped=start!=0 or end!=total_samples,
                reference_sha256=sha(reference_path.read_bytes()),
                reference_file='reference.wav', reference_peak=float(np.max(abs(reference))),
                reference_rms=rms,
                current_tiny_duration_supported=len(reference)<=65535,
                hq4_minimum_frames=math.ceil(len(reference)/256),
                hq4_minimum_stream_bytes=2*math.ceil(len(reference)/256)+4,
                hq4_stream_budget_bytes=617)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs', nargs='+', type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--start-seconds', type=float, help='Explicit user-selected excerpt, one input only')
    p.add_argument('--end-seconds', type=float, help='Explicit user-selected excerpt, one input only')
    a = p.parse_args()
    slugs = [re.sub('[^a-z0-9_-]+', '-', path.stem.lower()).strip('-') for path in a.inputs]
    if any(not slug for slug in slugs) or len(set(slugs)) != len(slugs):
        p.error('Source filenames need distinct nonempty ASCII identifiers')
    if (a.start_seconds is not None or a.end_seconds is not None) and len(a.inputs) != 1:
        p.error('Explicit excerpt selection requires exactly one input')
    reports = [prepare(path, a.output/slug, start_seconds=a.start_seconds, end_seconds=a.end_seconds)
               for path, slug in zip(a.inputs, slugs)]
    manifest = dict(schema='new-speech-inputs-v1',
                    source_sha256_normalized_lf=sha(Path(__file__).read_text(encoding='utf-8').encode()),
                    runtime={name:importlib.metadata.version(name) for name in ('numpy','scipy','soundfile')},
                    clips=reports)
    (a.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n',
                                         encoding='utf-8', newline='\n')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
