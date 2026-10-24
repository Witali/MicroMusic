"""One bounded24-seed phase-insensitive pulsebook screen; no annealing."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT/'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from q3_pulsebook import legacy_tables, validate
from q3_pulsebook_seed import minimum_phase_initialize

spec = importlib.util.spec_from_file_location('minimum_phase_seed_evaluation', ROOT/'tools/probe-q3-pulsebook.py')
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
spec.loader.exec_module(search)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--model', action='append', required=True, help='Label=Q3 or rounded model path; at most2')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--retain', type=Path)
    a = p.parse_args()
    if len(a.model) > 2:
        p.error('This isolated follow-up is limited to2bases and24seeds')
    reference, sr = sf.read(a.reference, dtype='float64')
    if sr != 7500 or reference.ndim != 1 or not np.all(np.isfinite(reference)):
        p.error('Expected complete unchanged finite mono7500 reference')
    objective = search.Objective(reference)
    report = dict(schema='q3-minphase-seeds-v1', reference_sha256=search.sha(a.reference),
        samples=len(reference), sample_rate=sr, target_stoi=.90, target_spectrogram_loss=.344975554,
        target_reached=False, annealing_proposals=0, models=[], avr_assembled=False, hardware_tested=False)
    for item in a.model:
        label, path = item.split('=', 1)
        source = json.loads(Path(path).read_text(encoding='utf-8'))
        nearest = bool(source.get('nearest', source['schema'] == 'hq4-q3-rounded-v1'))
        f, d = np.asarray(source['frames']), np.asarray(source['durations'])
        validate(f, d, legacy_tables(), samples=len(reference))
        f, d = f.astype(np.uint8), d.astype(np.uint16)
        budget = 613 if nearest else 615
        f, sharing = search.fit_budget(f, d, budget)
        for balance, selector, blend in itertools.product((False, True), ('incumbent', 'cluster'), (.25, .5, 1.)):
            name = f'{label}-balanced{int(balance)}-{selector}-blend{blend:g}'
            model, training = minimum_phase_initialize(reference, f, d, nearest=nearest,
                balance=balance, selector=selector, blend=blend, stream_budget=budget)
            state = search.State(np.asarray(model['frames'], np.uint8), d.copy(),
                np.asarray(model['pulsebook'], np.int8), nearest, 1)
            score = objective.evaluate(state)
            state.score = score
            row = dict(id=name, score=score, physical_valid=score is not None,
                training=training, source_sha256=search.sha(path), coefficient_reuse=sharing)
            if score is not None:
                search.export_state(a.output/name, state, objective, report['reference_sha256'])
                row['model'] = f'{name}/model.json'
                row['energy'] = objective.energy(score)
                report['target_reached'] |= bool(score['target_met'])
            report['models'].append(row)
            print(json.dumps(dict(id=name, score=score)), flush=True)
    valid = [row for row in report['models'] if row['physical_valid']]
    report['best_by_joint_target'] = [row['id'] for row in sorted(valid, key=lambda r:r['energy'])[:4]]
    report['best_by_stoi'] = [row['id'] for row in sorted(valid, key=lambda r:-r['score']['stoi'])[:4]]
    sources = [Path(__file__), CODEC/'q3_pulsebook_seed.py', CODEC/'q3_phasebook.py', CODEC/'q3_pulsebook.py',
               ROOT/'tools/probe-q3-pulsebook.py', CODEC/'spectrogram_objective.py']
    report['source_sha256_normalized_lf'] = {path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() for path in sources}
    search.save(a.output/'report.json', report)
    if a.retain:
        search.save(a.retain/'report.json', report)
        for name in dict.fromkeys(report['best_by_joint_target']+report['best_by_stoi']):
            for filename in ('model.json', 'quality.json'):
                search.save(a.retain/name/filename, json.loads((a.output/name/filename).read_text(encoding='utf-8')))
    print(json.dumps(dict(target_reached=report['target_reached'], physical_valid=len(valid),
        total=len(report['models']), best_by_stoi=report['best_by_stoi'], best_by_joint_target=report['best_by_joint_target'])), flush=True)


if __name__ == '__main__':
    main()
