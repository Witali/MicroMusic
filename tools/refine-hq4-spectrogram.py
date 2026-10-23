"""Automatically refit exact HQ4 against spectral ridges and broad envelopes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import pack_stream, unpack_stream
from hq4_phase import audit
from hq4_speech_search import SpeechObjective, SpeechSearch
from model import decode
from spectrogram_objective import SpectrogramObjective, VERSION


class Objective(SpeechObjective):
    def __init__(self, reference, sr=7500):
        super().__init__(reference, sr)
        self.detail = SpectrogramObjective(reference, sr)

    def evaluate(self, frames, durations):
        result = super().evaluate(frames, durations)
        if result is None:
            return None
        info = audit(frames, durations)
        if any(info[key] for key in ('subtraction_wraps', 'state_addition_wraps', 'negative_128_multiplication')):
            return None
        pcm = decode(frames, durations, 0)
        detail = self.detail.evaluate((pcm.astype(float)-128)/128)
        result.update(detail)
        result['loss'] = detail['spectrogram_loss']
        return result


class Search(SpeechSearch):
    """A scalar improvement cannot hide new missing or unsupported energy."""
    components = ('fine_log_error', 'envelope_error', 'unsupported_energy', 'missing_energy')

    def feasible(self, score):
        return (super().feasible(score)
                and all(score[key] <= self.baseline[key]+1e-12 for key in self.components))

    def energy(self, score):
        return super().energy(score)+4*sum(max(0., score[key]-self.baseline[key]) for key in self.components)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--stream', required=True, type=Path)
    p.add_argument('--guard-stream', type=Path, help='Frozen baseline for both intelligibility floors and legacy spectral ceilings')
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--proposals', default=6000, type=int)
    p.add_argument('--seed', default=23170, type=int)
    p.add_argument('--build', action='store_true')
    p.add_argument('--avr-bin', type=Path)
    p.add_argument('--node', default='node')
    a = p.parse_args()
    if a.proposals < 0:
        p.error('Proposals must be nonnegative')
    reference, sr = sf.read(a.reference)
    objective = Objective(reference, sr)
    frames, durations = unpack_stream(a.stream.read_bytes())
    guard_path = a.guard_stream or a.stream
    guard_frames, guard_durations = unpack_stream(guard_path.read_bytes())
    if int(durations.sum()) != len(reference) or int(guard_durations.sum()) != len(reference):
        p.error('Input and frozen guard streams must preserve the complete reference duration')
    guard = objective.evaluate(guard_frames, guard_durations)
    search = Search(objective, frames, durations, seed=a.seed, baseline_score=guard)
    for i in range(a.proposals):
        search.step()
        if (i+1)%1500 == 0:
            print(json.dumps(dict(proposals=i+1, best=search.best[2])), flush=True)
    frames, durations, final = search.best
    pcm = decode(frames, durations, 0)
    payload = pack_stream(frames, durations)
    a.output.mkdir(parents=True, exist_ok=True)
    sha = lambda data: hashlib.sha256(data).hexdigest()
    model = dict(schema='hq4-spectrogram-refit-v1', sample_rate=sr, samples=len(reference),
                 frames=frames.tolist(), durations=durations.tolist(), reference_sha256=sha(a.reference.read_bytes()),
                 stream_sha256=sha(payload))
    sources = [Path(__file__), CODEC/'spectrogram_objective.py', CODEC/'hq4_speech_search.py',
               CODEC/'speech_spectrum.py', CODEC/'auto_encoder.py', CODEC/'model.py', CODEC/'hq4_phase.py', CODEC/'hq4_core.py']
    report = dict(schema='hq4-spectrogram-refit-v1', objective_version=VERSION, frozen_baseline=guard,
                  initial=search.initial, final=final, proposals=a.proposals, seed=a.seed,
                  guard_stream_sha256=sha(guard_path.read_bytes()), input_stream_sha256=sha(a.stream.read_bytes()),
                  reference_sha256=model['reference_sha256'], pcm_sha256=sha(pcm.tobytes()),
                  stream_sha256=sha(payload), stream_bytes=len(payload), decoder_bytes=406,
                  human_listening_verified=False, hardware_tested=False,
                  sources_sha256_normalized_lf={path.relative_to(ROOT).as_posix():sha(path.read_text(encoding='utf-8').encode()) for path in sources},
                  history=search.history)
    for name, value in (('model.json', model), ('quality.json', report)):
        (a.output/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
    (a.output/'speech.hq').write_bytes(payload)
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(a.output/'decoded.wav', (pcm.astype(float)-128)/128, sr, subtype='PCM_16')
    original = reference
    before = (decode(*unpack_stream(guard_path.read_bytes()), 0).astype(float)-128)/128
    after = (pcm.astype(float)-128)/128
    signals = [sosfilt(objective.hp, x) for x in (original, before, after)]
    signals = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-20) for x in signals]
    scale = .85/max(float(np.max(abs(x))) for x in signals)
    for name, signal in zip(('original', 'before', 'after'), signals):
        sf.write(a.output/(name+'-matched.wav'), signal*scale, sr, subtype='PCM_16')
    sf.write(a.output/'comparison.wav', np.concatenate([part for x in signals for part in (x*scale, np.zeros(2250))]), sr, subtype='PCM_16')
    if a.build:
        spec = importlib.util.spec_from_file_location('spectrogram_builder', ROOT/'tools/build-hq4-oneshot.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        report = builder.build('spectrogram-refit', a.output/'avr', a.avr_bin, a.node,
                               stream=a.output/'speech.hq', expected_samples=len(reference))
        print(json.dumps(dict(avr=report['status'], flash=report['flashBytes'])), flush=True)
    print(json.dumps(final), flush=True)


if __name__ == '__main__':
    main()
