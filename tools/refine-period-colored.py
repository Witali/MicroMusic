#!/usr/bin/env python3
"""Train three noise FIRs and jointly refine period/noise frames on three clips."""
import argparse
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import sosfilt

ROOT = Path(__file__).resolve().parents[1]
CODEC = ROOT / 'ATtiny13A/Sound/codec'
sys.path.insert(0, str(CODEC))
from auto_encoder import SpectralObjective
from joint_period import JointSearch
from colored_period import learn_colored_model, ColoredSynthesis, decode_colored, pack_colored, unpack_colored
from period_residual import decode_residual, pack_residual
from refine_period_helpers import atomic_json, digest, matched_audio


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--models', type=Path, default=ROOT / 'ATtiny13A/Sound/research/period-joint')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--clip', choices=['all', 'chego', 'otvechaesh', 'vinni'], default='all')
    p.add_argument('--proposals', type=int, default=16000)
    p.add_argument('--weight', type=float, default=8.)
    p.add_argument('--resume', action='store_true')
    a = p.parse_args()
    if a.proposals < 0 or a.weight <= 0:
        p.error('Invalid proposals or weight')
    sources = [CODEC / name for name in ('colored_period.py', 'joint_period.py', 'period_residual.py', 'period_wave.py', 'auto_encoder.py')]
    sources += [Path(__file__), ROOT / 'tools/refine_period_helpers.py']
    fingerprints = {str(path.relative_to(ROOT)).replace('\\', '/'):digest(path.read_text(encoding='utf-8').encode()) for path in sources}
    runtime = {name:importlib.metadata.version(name) for name in ('numpy', 'scipy', 'pystoi', 'soundfile')}
    runtime['python'] = sys.version.split()[0]
    manifest = json.loads((ROOT / 'ATtiny13A/Sound/audio-references.json').read_text(encoding='utf-8'))
    reports = []
    for clip in manifest['clips']:
        if a.clip != 'all' and a.clip != clip['id']:
            continue
        source = a.references / clip['id'] / 'original.wav'
        if digest(source.read_bytes()) != clip['sha256']:
            raise ValueError('Reference hash mismatch')
        reference, sr = sf.read(source)
        objective = SpectralObjective(reference, sr)
        model_path = a.models / clip['id'] / 'model.json'
        legacy = json.loads(model_path.read_text(encoding='utf-8'))
        if legacy['base']['samples'] != len(reference):
            raise ValueError('Duration mismatch')
        model = learn_colored_model(legacy, reference)
        if not np.allclose(decode_residual(legacy), decode_colored(model), rtol=0, atol=1e-12):
            raise AssertionError('New format cannot exactly preserve the previous residual')
        output = a.output / clip['id']
        output.mkdir(parents=True, exist_ok=True)
        inputs = dict(reference_sha256=clip['sha256'], initial_model_sha256=digest(model_path.read_bytes()), sources_sha256_normalized_lf=fingerprints)
        saved = json.loads((output / 'checkpoint.json').read_text(encoding='utf-8')) if a.resume else None
        if saved and saved['inputs'] != inputs:
            raise ValueError('Checkpoint input/source hashes differ')
        search = JointSearch(model, objective, stoi_weight=a.weight, cache_factory=ColoredSynthesis,
                             checkpoint=saved['search'] if saved else None)

        def save(status):
            elite = search.export()
            payload = pack_colored(elite)
            exact = decode_colored(unpack_colored(payload))
            if not np.array_equal(exact, decode_colored(elite)):
                raise AssertionError('Colored payload roundtrip changed audio')
            score = search.score(exact)
            report = dict(schema='colored-period-report-v1', clip_id=clip['id'], inputs=inputs, runtime=runtime,
                          config=search.config, initial=search.initial, final=score, proposals=search.proposals,
                          evaluated=search.evaluated, improvements=search.improvements, history=search.history,
                          data_bytes=len(payload), extra_data_bytes=len(payload)-len(pack_residual(legacy)),
                          available_flash_after_data=1024-len(payload), payload_sha256=digest(payload),
                          avr_assembled=False, hardware_verified=False, status=status, filter_seed=23069)
            atomic_json(output / 'model.json', elite)
            atomic_json(output / 'quality.json', report)
            atomic_json(output / 'checkpoint.json', dict(inputs=inputs, search=search.checkpoint()))
            print(json.dumps(dict(clip=clip['id'], proposals=search.proposals, **score)), flush=True)
            return report

        try:
            while search.proposals < a.proposals:
                search.step()
                if search.proposals % 4000 == 0:
                    save('searching')
        except KeyboardInterrupt:
            save('interrupted')
            return
        reports.append(save('complete'))
        matched_audio(output, dict(Original=reference, Before=decode_residual(legacy), Colored=decode_colored(search.export())), objective,
                      ('Original', 'Before', 'Original', 'Colored'))
    if any(digest(path.read_text(encoding='utf-8').encode()) != fingerprints[str(path.relative_to(ROOT)).replace('\\', '/')] for path in sources):
        raise RuntimeError('Encoder sources changed during the experiment')
    atomic_json(a.output / 'quality.json', dict(schema='colored-period-experiment-v1', clips=reports))


if __name__ == '__main__':
    main()
