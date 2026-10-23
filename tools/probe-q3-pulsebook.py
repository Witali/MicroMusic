"""Bounded joint search of exact Q3 pulsebook+frames against original speech.

Target failures remain explicit. Pareto exports are research candidates only;
the separate assembler/emulator builder must qualify any complete firmware.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
from pystoi import stoi
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0,str(CODEC))
from q3_pulsebook import SCHEMA, legacy_tables, render, validate
from hq4_core import pack_stream
from hq4_speech_search import proposal as frame_proposal, deterministic_estoi
from spectrogram_objective import SpectrogramObjective
from harmonic_tracks import HarmonicTrackObjective


def save(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class State:
    frames: np.ndarray
    durations: np.ndarray
    book: np.ndarray
    nearest: bool
    tilt: int
    score: dict = None


def fit_budget(frames, durations, budget):
    """Real coefficient-half reuse, never dropping or shortening samples."""
    frames = frames.copy()
    changes = []
    while len(pack_stream(frames,durations)) > budget:
        best = None
        old_size = len(pack_stream(frames,durations))
        for index in range(1,len(frames)):
            for begin in (2,4):
                if np.array_equal(frames[index,begin:begin+2],frames[index-1,begin:begin+2]):
                    continue
                trial = frames.copy()
                trial[index,begin:begin+2] = trial[index-1,begin:begin+2]
                size = len(pack_stream(trial,durations))
                if size >= old_size:
                    continue
                before, after = frames[index,begin:begin+2].astype(int),trial[index,begin:begin+2].astype(int)
                distance = int(abs((before & 15)-(after & 15)).sum()+abs((before >> 4)-(after >> 4)).sum())
                key = (distance/(old_size-size),distance,size,index,begin)
                if best is None or key < best[0]:
                    best = key,trial,index,begin,size
        if best is None:
            raise ValueError('Unable to fit the model by coefficient-half reuse')
        _,frames,index,begin,size = best
        changes.append(dict(frame=index,coefficient_byte=begin,before_bytes=old_size,after_bytes=size))
    return frames,changes


class Objective:
    def __init__(self, reference, *, stoi_target=.9, spectrum_target=.344975554,
                 rounded_budget=613, floor_budget=615):
        self.reference = np.asarray(reference,dtype=float)
        self.spectral = SpectrogramObjective(reference)
        self.stoi_target,self.spectrum_target = stoi_target,spectrum_target
        self.rounded_budget,self.floor_budget = rounded_budget,floor_budget
        self.invalid = dict(layout=0,wrap=0,peak=0,steps=0)

    def budget(self,state):
        return self.rounded_budget if state.nearest else self.floor_budget

    def evaluate(self,state):
        try:
            payload = validate(state.frames,state.durations,state.book,len(self.reference),self.budget(state))
        except ValueError:
            self.invalid['layout'] += 1
            return None
        pcm,counts = render(state.frames,state.durations,state.book,state.tilt,state.nearest)
        if np.any(counts):
            self.invalid['wrap'] += 1
            return None
        signed = pcm.astype(np.int16)-128
        peak,steps = int(abs(signed).max()),int(np.count_nonzero(abs(np.diff(signed)) >= 48))
        if peak > 115:
            self.invalid['peak'] += 1
            return None
        if steps:
            self.invalid['steps'] += 1
            return None
        audio = signed.astype(float)/128
        result = dict(stoi=float(stoi(self.reference,audio,7500)),**self.spectral.evaluate(audio),
            stream_bytes=len(payload),peak_signed=peak,steps_ge48=steps,
            wrap_counts=counts.tolist(),raw_mean=float(audio.mean()),raw_rms=float(np.sqrt(np.mean(audio**2))))
        result['target_met'] = bool(result['stoi'] >= self.stoi_target and result['spectrogram_loss'] <= self.spectrum_target)
        return result

    def energy(self,score):
        return score['spectrogram_loss']+6*max(0.,self.stoi_target-score['stoi'])


def mutate(anchor,rng):
    f,d,b = anchor.frames.copy(),anchor.durations.copy(),anchor.book.copy()
    kind = rng.randrange(100)
    if kind < 58:
        f,d = frame_proposal(f,d,rng)
    elif kind < 82:
        row,column = rng.randrange(4),rng.randrange(16)
        b[row,column] = max(-7,min(7,int(b[row,column])+rng.choice((-2,-1,1,2))))
    elif kind < 92:
        row,column,delta = rng.randrange(4),rng.randrange(16),rng.choice((-1,1))
        for index in range(column,min(16,column+rng.randint(2,4))):
            b[row,index] = max(-7,min(7,int(b[row,index])+delta))
    else:
        # Joint source/gain/selector edits can cross a single-coordinate barrier.
        row = rng.randrange(4)
        for _ in range(rng.randint(1,3)):
            column = rng.randrange(16)
            b[row,column] = max(-7,min(7,int(b[row,column])+rng.choice((-1,1))))
        indices = np.flatnonzero((f[:,1] >> 4) == row)
        if len(indices):
            index = int(rng.choice(indices.tolist()))
            gain = max(0,min(15,(int(f[index,1]) & 15)+rng.choice((-1,1))))
            f[index,1] = (int(f[index,1]) & 48)|gain
    return State(f,d,b,anchor.nearest,anchor.tilt)


def pareto_add(archive,state):
    score = state.score
    if any(old.score['stoi'] >= score['stoi'] and old.score['spectrogram_loss'] <= score['spectrogram_loss'] for old in archive):
        return archive
    archive = [old for old in archive if not (score['stoi'] >= old.score['stoi'] and score['spectrogram_loss'] <= old.score['spectrogram_loss'])]
    archive.append(state)
    if len(archive) > 32:
        archive.sort(key=lambda x:x.score['stoi'])
        # Preserve the intelligibility/spectrum ends; remove the most crowded
        # internal frontier point rather than deleting an extreme candidate.
        index = min(range(1,len(archive)-1),key=lambda i:
            archive[i+1].score['stoi']-archive[i-1].score['stoi']+
            archive[i-1].score['spectrogram_loss']-archive[i+1].score['spectrogram_loss'])
        archive.pop(index)
    return archive


def export_state(folder,state,objective,reference_sha,*,final_metrics=False):
    folder.mkdir(parents=True,exist_ok=True)
    payload = validate(state.frames,state.durations,state.book,len(objective.reference),objective.budget(state))
    pcm,counts = render(state.frames,state.durations,state.book,state.tilt,state.nearest)
    model = dict(schema=SCHEMA,sample_rate=7500,samples=len(pcm),tilt_shift=state.tilt,nearest=state.nearest,
        pulsebook=state.book.tolist(),frames=state.frames.tolist(),durations=state.durations.tolist(),
        reference_sha256=reference_sha,stream_budget=objective.budget(state))
    save(folder/'model.json',model)
    (folder/'speech.hq').write_bytes(payload)
    (folder/'eeprom.bin').write_bytes(np.asarray(state.book,dtype=np.int8).tobytes())
    (folder/'expected.raw').write_bytes(pcm.tobytes())
    audio = (pcm.astype(float)-128)/128
    sf.write(folder/'decoded.wav',audio,7500,subtype='FLOAT')
    score = dict(state.score)
    if final_metrics:
        score['estoi'] = deterministic_estoi(objective.reference,audio,7500)
        score['harmonic_metrics'] = HarmonicTrackObjective(objective.reference).evaluate(audio)
    score.update(stream_sha256=hashlib.sha256(payload).hexdigest(),pcm_sha256=hashlib.sha256(pcm.tobytes()).hexdigest(),
        eeprom_bytes=64,avr_assembled=False,avr_verified=False,hardware_tested=False,
        size_policy='Actual stream+64EEPROM; separate exact assembler must confirm fullFlash size and cycles')
    save(folder/'quality.json',score)
    return score


def run(reference_path, model_paths, output, *, proposals=6000, seed=23143, extra_seed_directory=None,
        stoi_target=.9,spectrum_target=.344975554,rounded_budget=613,floor_budget=615):
    started = time.perf_counter()
    reference_path,output = Path(reference_path),Path(output)
    reference,sr = sf.read(reference_path,dtype='float64')
    if sr != 7500 or reference.ndim != 1 or len(reference) < 3072:
        raise ValueError('Expected complete mono7500Hz reference')
    objective = Objective(reference,stoi_target=stoi_target,spectrum_target=spectrum_target,
        rounded_budget=rounded_budget,floor_budget=floor_budget)
    archive,initial,seen = [],[],set()

    def add_seed(path):
        path = Path(path)
        if str(path.resolve()) in seen:
            return
        seen.add(str(path.resolve()))
        model = json.loads(path.read_text(encoding='utf-8'))
        nearest = bool(model.get('nearest',model['schema'] == 'hq4-q3-rounded-v1'))
        state = State(np.asarray(model['frames'],np.uint8),np.asarray(model['durations'],np.uint16),
            np.asarray(model.get('pulsebook',legacy_tables()),np.int8),nearest,int(model.get('tilt_shift',1)))
        original_bytes = len(pack_stream(state.frames,state.durations))
        state.frames,changes = fit_budget(state.frames,state.durations,objective.budget(state))
        state.score = objective.evaluate(state)
        initial.append(dict(source=path.name,source_sha256=sha(path),nearest=nearest,original_stream_bytes=original_bytes,
            coefficient_reuse=changes,score=state.score))
        if state.score is not None:
            archive[:] = pareto_add(archive,state)
        print(json.dumps(dict(seed=path.name,nearest=nearest,score=state.score)),flush=True)

    for path in model_paths:
        add_seed(path)
    if not archive:
        raise ValueError('No seed passes the hard arithmetic/peak/size guards')
    rng = random.Random(seed)
    current = min(archive,key=lambda state:objective.energy(state.score))
    accepted = evaluated = 0
    history = []
    for index in range(proposals):
        if extra_seed_directory is not None and index % 500 == 0:
            for path in sorted(Path(extra_seed_directory).glob('**/model.json')):
                add_seed(path)
        elite = min(archive,key=lambda state:objective.energy(state.score))
        if index % 1500 == 0:
            current = rng.choice(archive)
        anchor = elite if rng.random() < .5 else (rng.choice(archive) if rng.random() < .3 else current)
        candidate = mutate(anchor,rng)
        candidate.score = objective.evaluate(candidate)
        if candidate.score is not None:
            evaluated += 1
            archive = pareto_add(archive,candidate)
            temperature = .008*.05**((index % 1500)/1499)
            delta = objective.energy(candidate.score)-objective.energy(current.score)
            if delta <= 0 or rng.random() < math.exp(-min(700,delta/temperature)):
                current = candidate
                accepted += 1
        if (index+1) % 500 == 0:
            elite = min(archive,key=lambda state:objective.energy(state.score))
            record = dict(proposals=index+1,evaluated=evaluated,accepted=accepted,pareto=len(archive),
                best_balanced=elite.score,best_stoi=max(s.score['stoi'] for s in archive),
                best_spectrum=min(s.score['spectrogram_loss'] for s in archive),elapsed_seconds=time.perf_counter()-started)
            history.append(record)
            save(output/'progress.json',record)
            export_state(output/'balanced',elite,objective,sha(reference_path))
            print(json.dumps(record),flush=True)
    elite = min(archive,key=lambda state:objective.energy(state.score))
    finalists = dict(balanced=elite,best_stoi=max(archive,key=lambda s:s.score['stoi']),
        best_spectrum=min(archive,key=lambda s:s.score['spectrogram_loss']))
    passing = [s for s in archive if s.score['target_met']]
    if passing:
        finalists['target_met'] = min(passing,key=lambda s:s.score['spectrogram_loss'])
    results = {name:export_state(output/name,state,objective,sha(reference_path),final_metrics=True) for name,state in finalists.items()}
    for index,state in enumerate(sorted(archive,key=lambda s:s.score['stoi'])):
        export_state(output/'pareto'/f'{index:02d}',state,objective,sha(reference_path))
    report = dict(schema='q3-pulsebook-search-v1',reference_sha256=sha(reference_path),samples=len(reference),
        targets=dict(stoi=stoi_target,spectrogram_loss=spectrum_target),target_met=bool(passing),
        proposals=proposals,evaluated=evaluated,accepted=accepted,seed=seed,initial=initial,finalists=results,
        guard_rejections=objective.invalid,history=history,elapsed_seconds=time.perf_counter()-started,
        rounded_stream_budget=rounded_budget,floor_stream_budget=floor_budget,eeprom_bytes=64,
        avr_qualified=False,public_firmware_changed=False,
        objective_policy='Original STOI+wholeSpectrogramObjective; no baseline-quality ceilings, waveform/DC/gain postprocessing or manual frequency masks',
        source_sha256_normalized_lf={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for p in (Path(__file__),CODEC/'q3_pulsebook.py',CODEC/'spectrogram_objective.py',CODEC/'hq4_speech_search.py')})
    save(output/'report.json',report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',required=True,type=Path)
    p.add_argument('--model',required=True,type=Path,action='append')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--proposals',type=int,default=6000)
    p.add_argument('--seed',type=int,default=23143)
    p.add_argument('--extra-seed-directory',type=Path)
    p.add_argument('--stoi-target',type=float,default=.9)
    p.add_argument('--spectrum-target',type=float,default=.344975554)
    p.add_argument('--rounded-stream-budget',type=int,default=613)
    p.add_argument('--floor-stream-budget',type=int,default=615)
    a = p.parse_args()
    run(a.reference,a.model,a.output,proposals=a.proposals,seed=a.seed,extra_seed_directory=a.extra_seed_directory,
        stoi_target=a.stoi_target,spectrum_target=a.spectrum_target,rounded_budget=a.rounded_stream_budget,floor_budget=a.floor_stream_budget)


if __name__ == '__main__':
    main()
