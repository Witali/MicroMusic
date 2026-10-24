"""Bounded inverse-lattice pulsebook seed screen; no annealing or target edits."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import linear_sum_assignment
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from hq4_core import pack_stream
from q3_pulsebook import legacy_tables, validate
from q3_pulsebook_seed import initialize

spec = importlib.util.spec_from_file_location('pulsebook_seed_evaluation', ROOT/'tools/probe-q3-pulsebook.py')
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--model', action='append', required=True, help='Label=explicit Q3 or rounded model path')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--iterations', type=int, default=8)
    p.add_argument('--retain', type=Path)
    a = p.parse_args()
    reference, sr = sf.read(a.reference, dtype='float64')
    if sr != 7500 or reference.ndim != 1 or not np.all(np.isfinite(reference)):
        p.error('Expected unchanged complete finite mono7500 reference')
    objective = search.Objective(reference)
    started = time.perf_counter()
    report = dict(schema='q3-pulsebook-inverse-seeds-v1',
        reference_sha256=search.sha(a.reference), samples=len(reference), sample_rate=sr,
        target_stoi=.90, target_spectrogram_loss=.344975554,
        target_reached=False, seed_configurations=[], models=[], annealing_proposals=0,
        policy='Full source untouched; fixed16 native-sample lag windows, exact reset convention; no source at decode',
        avr_assembled=False, hardware_tested=False)
    def emit(name, prefix, f, durations, book, nearest, scale, training):
        state = search.State(f, durations.copy(), book.copy(), nearest, 1)
        score = objective.evaluate(state)
        state.score = score
        row = dict(id=name, configuration=prefix, gain_scale=scale, score=score,
                   physical_valid=score is not None, avr_assembled=False)
        if score is not None:
            folder = a.output/name
            search.export_state(folder, state, objective, report['reference_sha256'])
            search.save(folder/'seed-training.json', training)
            row['model'] = f'{name}/model.json'
            row['energy'] = objective.energy(score)
            report['target_reached'] |= bool(score['target_met'])
        report['models'].append(row)
        print(json.dumps(dict(id=name, score=score)), flush=True)
    for item in a.model:
        label, path = item.split('=', 1)
        path = Path(path)
        original = json.loads(path.read_text(encoding='utf-8'))
        nearest = bool(original.get('nearest', original['schema'] == 'hq4-q3-rounded-v1'))
        frames, durations = np.asarray(original['frames']), np.asarray(original['durations'])
        validate(frames, durations, legacy_tables(), samples=len(reference))
        frames = frames.astype(np.uint8)
        durations = durations.astype(np.uint16)
        budget = 613 if nearest else 615
        frames, changes = search.fit_budget(frames, durations, budget)
        for inverse, local, balance in itertools.product(('float', 'byte'), (False, True), (False, True)):
            config = dict(inverse=inverse, local_pitch=local, balance=balance)
            model, training = initialize(reference, frames, durations, nearest=nearest,
                iterations=a.iterations, stream_budget=budget, **config)
            prefix = f'{label}-{inverse}-pitch{int(local)}-balanced{int(balance)}'
            report['seed_configurations'].append(dict(id=prefix, source_sha256=search.sha(path),
                coefficient_reuse=changes, training=training, nearest=nearest))
            base_frames = np.asarray(model['frames'], np.uint8)
            book = np.asarray(model['pulsebook'], np.int8)
            for scale in (1., .75, .5, .25):
                name = f'{prefix}-gain{scale:g}'
                f = base_frames.copy()
                f[:, 1] = (f[:, 1] & 48) | np.clip(np.rint((f[:, 1] & 15)*scale), 0, 15).astype(np.uint8)
                emit(name, prefix, f, durations, book, nearest, scale, training)
            if not local:
                # Preserve the incumbent excitation energy/gains/modes while
                # introducing only a small part of each learned packet shape.
                legacy = legacy_tables().astype(float)
                unit_old = legacy/np.maximum(np.linalg.norm(legacy, axis=1)[:, None], 1e-20)
                unit_new = book.astype(float)/np.maximum(np.linalg.norm(book, axis=1)[:, None], 1e-20)
                correlations = unit_old@unit_new.T
                rows, columns = linear_sum_assignment(1-abs(correlations))
                aligned = np.zeros((4, 16))
                for row, column in zip(rows, columns):
                    aligned[row] = unit_new[column]*np.linalg.norm(legacy[row])*(1 if correlations[row, column] >= 0 else -1)
                for blend, scale in itertools.product((.25, .5, .75), (1., .75)):
                    blended = np.clip(np.rint((1-blend)*legacy+blend*aligned), -7, 7).astype(np.int8)
                    f = frames.copy()
                    f[:, 1] = (f[:, 1] & 48) | np.clip(np.rint((f[:, 1] & 15)*scale), 0, 15).astype(np.uint8)
                    name = f'{prefix}-preserve-blend{blend:g}-gain{scale:g}'
                    emit(name, prefix, f, durations, blended, nearest, scale,
                        dict(training, preservation_blend=blend, row_matching='One-to-one absolute-correlation assignment; sign and L2energy aligned to incumbent rows'))
    valid = [row for row in report['models'] if row['physical_valid']]
    report['best_by_joint_target'] = [row['id'] for row in sorted(valid, key=lambda r:r['energy'])[:8]]
    report['best_by_stoi'] = [row['id'] for row in sorted(valid, key=lambda r:-r['score']['stoi'])[:8]]
    sources = [Path(__file__), CODEC/'q3_pulsebook_seed.py', CODEC/'q3_phasebook.py',
               CODEC/'q3_pulsebook.py', ROOT/'tools/probe-q3-pulsebook.py',
               CODEC/'spectrogram_objective.py', CODEC/'hq4_core.py']
    report['source_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() for path in sources}
    report['invalid_counts'] = objective.invalid
    report['elapsed_seconds'] = time.perf_counter()-started
    search.save(a.output/'report.json', report)
    if a.retain:
        search.save(a.retain/'report.json', report)
        for name in dict.fromkeys(report['best_by_joint_target'][:4]+report['best_by_stoi'][:4]):
            for filename in ('model.json', 'quality.json', 'seed-training.json'):
                search.save(a.retain/name/filename, json.loads((a.output/name/filename).read_text(encoding='utf-8')))
    print(json.dumps(dict(target_reached=report['target_reached'], physical_valid=len(valid),
        total=len(report['models']), best_by_joint_target=report['best_by_joint_target'],
        best_by_stoi=report['best_by_stoi'])), flush=True)


if __name__ == '__main__':
    main()
