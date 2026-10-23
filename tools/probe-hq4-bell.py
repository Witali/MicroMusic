"""Try automatic high-frequency tonal candidates without weakening HQ4 speech.

This is a diagnostic refinement of a complete existing stream, not a bell or
phoneme classifier. The earliest strong group of persistent high-frequency
ridges supplies soft period alternatives, including periods 2..11 that the
original new-recording pitch initializer does not propose. No sample is cut.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
import soundfile as sf
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from hq4_core import pack_stream
from hq4_speech_search import validate
from model import decode
from new_hq4_encoder import Objective, validate_reference
from speech_spectrum import PersistentSpectrumObjective


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tonal_event(spectrum):
    """Earliest overlapping group of strong ridges, without semantic labels."""
    maximum = max((r['relative_energy'] for r in spectrum.ridges), default=0.)
    ridges = [r for r in spectrum.ridges
              if r['median_hz'] > spectrum.sr/12
              and r['relative_energy'] >= maximum*.01
              and r['maximum_hz']/r['minimum_hz'] < 1.1]
    if not ridges:
        raise ValueError('No strong persistent high-frequency tonal group was found')
    onset = min(r['start_seconds'] for r in ridges)
    # One 128-ms attack group can contain several modes of a physical strike.
    # This acoustic rule is independent of the recording or the spoken phrase.
    selected = [r for r in ridges if r['start_seconds'] <= onset+.128]
    return selected


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--proposals', type=int, default=5000)
    p.add_argument('--seed', type=int, default=23121)
    a = p.parse_args()
    if a.proposals < 0:
        p.error('Proposal count must be nonnegative')
    reference, sr = sf.read(a.reference)
    validate_reference(reference, sr)
    model = json.loads(a.model.read_text(encoding='utf-8'))
    if model['reference_sha256'] != sha(a.reference.read_bytes()):
        p.error('Model and reference differ')
    frames = np.asarray(model['frames'], np.int64)
    durations = np.asarray(model['durations'], np.int64)
    validate(frames, durations, len(reference))
    frames, durations = frames.astype(np.uint8), durations.astype(np.uint16)
    spectrum = PersistentSpectrumObjective(reference, sr)
    tracks = tonal_event(spectrum)
    mask = np.zeros_like(spectrum.target)
    for track in tracks:
        weight = np.sqrt(track['relative_energy'])
        for column, frequency in zip(track['frames'], track['frequency_hz']):
            center = int(round(frequency*spectrum.size/sr))
            for offset in range(-2, 3):
                if 0 <= center+offset < len(mask):
                    mask[center+offset, column] += weight*np.exp(-offset*offset/2)
    mask_sum = float(mask.sum())
    def tonal_error(pcm):
        magnitude = spectrum._candidate((pcm.astype(float)-128)/128)
        error = abs(np.log(np.maximum(magnitude, spectrum.floor))-spectrum.logged)
        return float(np.sum(mask*error)/mask_sum)
    objective = Objective(reference, sr)
    baseline = objective.evaluate(frames, durations, full=True)
    if baseline is None:
        p.error('Baseline exceeds peak or step constraints')
    first_pcm = decode(frames, durations, 0)
    first_error = tonal_error(first_pcm)
    best_error, best_score = first_error, baseline
    starts = np.r_[0, np.cumsum(durations)[:-1]]
    centers = (starts+durations/2)/sr
    active = [i for i, center in enumerate(centers)
              if any(track['start_seconds']-.034 <= center <= track['end_seconds']+.034 for track in tracks)]
    options = {}
    for index in active:
        periods = {int(frames[index, 0])}
        for track in tracks:
            if track['start_seconds']-.034 <= centers[index] <= track['end_seconds']+.034:
                for harmonic in range(1, 9):
                    period = round(sr*harmonic/track['median_hz'])
                    periods.update(period+delta for delta in (-1, 0, 1))
        options[index] = sorted(p for p in periods if 2 <= p <= 126)
    rng = random.Random(a.seed)
    accepted = []
    evaluated = 0
    for step in range(a.proposals):
        trial = frames.copy()
        index = rng.choice(active)
        kind = rng.randrange(100)
        if kind < 45:
            trial[index, 0] = rng.choice(options[index])
            if rng.random() < .2:
                trial[index, 1] = (trial[index, 1] & 15) | (rng.randrange(4) << 4)
        elif kind < 65:
            trial[index, 1] = ((trial[index, 1] & 48)
                               | np.clip(int(trial[index, 1] & 15)+rng.choice((-2, -1, 1, 2)), 0, 15))
        elif kind < 75:
            trial[index, 1] = (trial[index, 1] & 15) | (rng.randrange(4) << 4)
        else:
            coefficient = rng.randrange(8)
            byte, shift = 2+coefficient//2, (coefficient & 1)*4
            old = (int(frames[index, byte]) >> shift) & 15
            value = int(np.clip(old+rng.choice((-2, -1, 1, 2)), 0, 15))
            affected = [index]
            # Updating an entire existing sharing run usually preserves cost.
            if rng.random() < .6:
                for direction in (-1, 1):
                    j = index+direction
                    while (j in options and ((int(frames[j, byte]) >> shift) & 15) == old):
                        affected.append(j)
                        j += direction
            for j in affected:
                trial[j, byte] = (int(trial[j, byte]) & (15 if shift else 240)) | (value << shift)
        if np.array_equal(trial, frames) or len(pack_stream(trial, durations)) > 617:
            continue
        evaluated += 1
        pcm = decode(trial, durations, 0)
        error = tonal_error(pcm)
        if error >= best_error-1e-8:
            continue
        score = objective.evaluate(trial, durations, full=True)
        if (score is None or score['stoi'] < baseline['stoi']-1e-12
                or score['estoi'] < baseline['estoi']-1e-12
                or score['loss'] > baseline['loss']*1.03+1e-12):
            continue
        frames, best_error, best_score = trial, error, score
        accepted.append(dict(proposal=step+1, tonal_error=error, **score))
        if len(accepted) % 10 == 0:
            print(json.dumps(accepted[-1]), flush=True)
    a.output.mkdir(exist_ok=True, parents=True)
    payload = pack_stream(frames, durations)
    pcm = decode(frames, durations, 0)
    export = dict(model, schema='hq4-tonal-probe-v1', frames=frames.tolist(),
                  stream_sha256=sha(payload), baseline_model_sha256=sha(a.model.read_bytes()))
    sources = ['tools/probe-hq4-bell.py', 'ATtiny13A/Sound/codec/new_hq4_encoder.py',
               'ATtiny13A/Sound/codec/speech_spectrum.py', 'ATtiny13A/Sound/codec/model.py',
               'ATtiny13A/Sound/codec/auto_encoder.py', 'ATtiny13A/Sound/codec/hq4_core.py',
               'ATtiny13A/Sound/codec/hq4_speech_search.py']
    report = dict(schema='hq4-tonal-probe-v1', baseline=baseline, final=best_score,
                  initial_tonal_error=first_error, final_tonal_error=best_error,
                  samples=len(reference), complete_recording=True, seed=a.seed,
                  proposals=a.proposals, evaluated=evaluated, improvements=len(accepted),
                  selected_tracks=tracks, changed_frames=np.flatnonzero(np.any(frames != np.asarray(model['frames']), axis=1)).tolist(),
                  assembled=False, hardware_tested=False, decoder_bytes=406,
                  stream_bytes=len(payload), estimated_flash_bytes=(406+len(payload)+2)//2*2,
                  reference_sha256=sha(a.reference.read_bytes()), baseline_model_sha256=sha(a.model.read_bytes()),
                  stream_sha256=sha(payload), pcm_sha256=sha(pcm.tobytes()), history=accepted,
                  sources_sha256_normalized_lf={name: sha((ROOT/name).read_text(encoding='utf-8').encode('utf-8')) for name in sources})
    for name, data in (('model.json', export), ('training.json', report)):
        (a.output/name).write_text(json.dumps(data, indent=2)+'\n', encoding='utf-8', newline='\n')
    (a.output/'speech.hq').write_bytes(payload)
    (a.output/'expected.raw').write_bytes(pcm.tobytes())
    sf.write(a.output/'decoded.wav', (pcm.astype(float)-128)/128, sr, subtype='PCM_16')
    filtered = [sosfilt(objective.hp, x) for x in (reference, (first_pcm.astype(float)-128)/128, (pcm.astype(float)-128)/128)]
    matched = [x*objective.rms/(np.sqrt(np.mean(x*x))+1e-10) for x in filtered]
    scale = .85/max(float(np.max(abs(x))) for x in matched)
    matched = [x*scale for x in matched]
    gap = np.zeros(round(.3*sr))
    sf.write(a.output/'comparison.wav', np.concatenate([part for i in (0, 1, 0, 2) for part in (matched[i], gap)]), sr, subtype='PCM_16')
    print(json.dumps(dict(stage='complete', initial_tonal_error=first_error,
                          final_tonal_error=best_error, improvements=len(accepted), **best_score)), flush=True)


if __name__ == '__main__':
    main()
