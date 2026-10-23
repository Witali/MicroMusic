"""Bounded learned-source experiment, independent of the retained Q3 firmware."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys

import numpy as np
import soundfile as sf
from pystoi import stoi
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import pack_stream
from hq4_q3 import render as legacy_render
from hq4_speech_search import deterministic_estoi, proposal
from harmonic_tracks import HarmonicTrackObjective
from q3_phasebook import render, learn_waves
from spectrogram_objective import SpectrogramObjective

spec = importlib.util.spec_from_file_location('phasebook_rate_seed', ROOT/'tools/probe-hq4-natural-timbre.py')
rate_helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rate_helper)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=1500)
    p.add_argument('--stream-budget', type=int, default=430)
    p.add_argument('--seed', type=int, default=23203)
    a = p.parse_args()
    reference, sr = sf.read(a.reference)
    model = json.loads(a.model.read_text(encoding='utf-8'))
    if sr != 7500 or reference.ndim != 1 or model.get('schema') != 'hq4-q3-v1' or model.get('tilt_shift') != 1:
        p.error('Expected the complete mono 7500-Hz original and explicit Q3/T1 control model')
    f, d = np.array(model['frames'], np.uint8), np.array(model['durations'], np.uint16)
    if int(d.sum()) != len(reference) or a.proposals < 0:
        p.error('Duration must retain the whole original, proposal count nonnegative')
    spectral, harmonic = SpectrogramObjective(reference), HarmonicTrackObjective(reference)
    def metrics(pcm):
        audio = (pcm.astype(float)-128)/128
        spectrum = spectral.evaluate(audio)
        tracks = harmonic.evaluate(audio)
        value = float(stoi(reference, audio, sr))
        matched = spectral.matched(audio)
        waveform_error = float(np.linalg.norm(matched-spectral.filtered)/np.linalg.norm(spectral.filtered))
        return dict(stoi=value, **spectrum, **tracks, waveform_nrmse=waveform_error,
                    objective=value-.35*spectrum['spectrogram_loss']-.12*tracks['harmonic_track_loss'])
    def evaluate(frames, durations, book):
        if (len(pack_stream(frames, durations)) > a.stream_budget or
                np.any((frames[:, 2:] & 15) == 0) or np.any((frames[:, 2:] >> 4) == 0)):
            return None
        pcm, counts = render(frames, durations, book)
        signed = pcm.astype(np.int16)-128
        if np.any(counts) or max(abs(signed)) > 115 or np.any(abs(np.diff(signed)) >= 48):
            return None
        return metrics(pcm)
    baseline_pcm = legacy_render(f, d, 1)[0]
    baseline = metrics(baseline_pcm)
    baseline['estoi'] = deterministic_estoi(reference, (baseline_pcm.astype(float)-128)/128, sr)
    first = None
    initial = []
    for length in (8, 16):
        book, groups = learn_waves(reference, f, d, length=length)
        frames = f.copy()
        voiced = frames[:, 0] > 0
        frames[voiced, 0] = np.clip(np.rint(2048/frames[voiced, 0].astype(float)), 16, 126).astype(np.uint8)
        frames = rate_helper.fit_rate(frames, d, a.stream_budget)
        for mapping in ('learned', 'old'):
            for gain_scale in (.25, .5, .75, 1.):
                trial = frames.copy()
                modes = groups if mapping == 'learned' else f[:, 1] >> 4
                trial[:, 1] = (modes.astype(np.uint8) << 4) | np.minimum(15, np.rint((f[:, 1] & 15)*gain_scale)).astype(np.uint8)
                score = evaluate(trial, d, book)
                initial.append(dict(length=length, mapping=mapping, gain_scale=gain_scale, score=score))
                if score is not None and (first is None or score['objective'] > first[3]['objective']):
                    first = trial, d.copy(), book.copy(), score
    if first is None:
        p.error('No clean learned-source seed fits the complete recording')
    best = first
    rng = random.Random(a.seed)
    history = []
    for i in range(a.proposals):
        frames, durations, book = best[0].copy(), best[1].copy(), best[2].copy()
        if rng.random() < .25:
            shape, index = rng.randrange(len(book)), rng.randrange(book.shape[1])
            other = (index+rng.choice((-1, 1))) % book.shape[1]
            delta = rng.choice((-2, -1, 1, 2))
            left, right = int(book[shape, index])+delta, int(book[shape, other])-delta
            if -31 <= left <= 31 and -31 <= right <= 31:
                book[shape, index], book[shape, other] = left, right
        else:
            frames, durations = proposal(frames, durations, rng)
        score = evaluate(frames, durations, book)
        if score is not None and score['objective'] > best[3]['objective']:
            best = frames, durations, book, score
            history.append(dict(proposal=i+1, **score))
        if (i+1) % 500 == 0:
            print(json.dumps(dict(proposals=i+1, **best[3])), flush=True)
    frames, durations, book, final = best
    pcm, counts = render(frames, durations, book)
    final['estoi'] = deterministic_estoi(reference, (pcm.astype(float)-128)/128, sr)
    final.update(stream_bytes=len(pack_stream(frames, durations)), table_bytes=int(book.size), intermediate_wraps=counts.tolist())
    ceilings = ('spectrogram_loss', 'fine_log_error', 'envelope_error', 'unsupported_energy', 'missing_energy', 'waveform_nrmse')
    failed = [key for key in ('stoi', 'estoi') if final[key] < baseline[key]-1e-12]
    failed += [key for key in ceilings if final[key] > baseline[key]+1e-12]
    output = a.output
    output.mkdir(parents=True, exist_ok=True)
    exported = dict(schema='hq4-q3-phasebook-v1', sample_rate=sr, samples=len(reference),
                    coefficient_scale=8, coefficient_range=[-7, 7], tilt_shift=1, dds_pitch_step=32,
                    frames=frames.tolist(), durations=durations.tolist(), waves=book.tolist())
    report = dict(schema='hq4-q3-phasebook-probe-v1', baseline=baseline, initial=initial,
        final=final, failed_guards=failed, accepted=not failed, proposals=a.proposals, seed=a.seed,
        stream_budget=a.stream_budget,
        history=history, avr_assembled=False, hardware_tested=False, human_listening_verified=False,
        reference_sha256=hashlib.sha256(a.reference.read_bytes()).hexdigest(),
        input_model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),
        estimated_bell_core_bytes_range=[550, 580],
        estimate_note='Engineering estimate only: replace original 78-byte pulse/noise block with DDS/LPM lookup and shared gain multiply; retain bell Q4 correction, add phase initialization; table is additional Flash, not EEPROM. No assembler or timing qualification.',
        sources_sha256_normalized_lf={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()
          for path in (Path(__file__), CODEC/'q3_phasebook.py', CODEC/'hq4_q3.py', CODEC/'hq4_speech_search.py', CODEC/'harmonic_tracks.py', CODEC/'spectrogram_objective.py', ROOT/'tools/probe-hq4-natural-timbre.py')})
    for name, value in (('model.json', exported), ('quality.json', report)):
        (output/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')
    (output/'speech.hq').write_bytes(pack_stream(frames, durations))
    (output/'expected.raw').write_bytes(pcm.tobytes())
    tracks = [spectral.filtered, spectral.matched((baseline_pcm.astype(float)-128)/128), spectral.matched((pcm.astype(float)-128)/128)]
    scale = .85/max(float(np.max(abs(x))) for x in tracks)
    for name, x in zip(('original', 'before', 'after'), tracks):
        sf.write(output/(name+'.wav'), x*scale, sr, subtype='PCM_16')
    sf.write(output/'comparison.wav', np.concatenate([part for x in tracks for part in (x*scale, np.zeros(2250))]), sr, subtype='PCM_16')
    print(json.dumps(dict(stage='complete', baseline=baseline, final=final, failed_guards=failed)), flush=True)


if __name__ == '__main__':
    main()
