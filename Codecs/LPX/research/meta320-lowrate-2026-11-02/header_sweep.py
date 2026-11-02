"""Preregistered same-byte pre/brightness grid; existing decoder feature only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import time

from encode_meta320 import Admission, save, BatchDecoder, recover_best_checkpoint
from pcm16_wav import write_pcm16_wav
from standard_metrics import pwm_pcm16
from voice_input import load_voice_wav


def run(reference, incumbent, output, common, only, speech=True):
    gate = Admission(reference, incumbent, output, common, only, speech)
    original_pre, original_bright = struct.unpack_from('<HH', incumbent, 12)
    pres = tuple(dict.fromkeys(min(16384, max(0, original_pre+offset))
                              for offset in (-4096, -2048, -1024, 0, 1024, 2048, 4096)))
    brightness = (0, 2048, 4096, 6144, 8192, 10240, 11469)
    save(gate.output/'header-plan-private.json', dict(pre_values=pres, brightness_values=brightness,
        original_pre=original_pre, original_brightness=original_bright,
        maximum_complete_attempts=49, payload_byte_identical=True, budget_kbps=gate.budget_kbps))
    started = time.perf_counter()
    for pre in pres:
        for bright in brightness:
            candidate = incumbent[:12]+struct.pack('<HH', pre, bright)+incumbent[16:]
            if candidate[16:] != incumbent[16:] or candidate[:12] != incumbent[:12] or len(candidate) != len(incumbent):
                raise AssertionError('Header sweep changed the payload or geometry')
            gate.add(candidate, origin=dict(pre_q14=pre, bright_q14=bright),
                work=dict(full_model_reconstructions=1, modeled_samples=len(reference)))
    best = gate.best()
    blob, pcm = gate.candidates[best['id']]
    if recover_best_checkpoint(gate.output)[0] != blob:
        raise AssertionError('Recovered header best differs')
    report = dict(schema='lpx-costed-existing-header-sweep-v1', selected_id=best['id'],
        selected_differs_from_incumbent=blob != incumbent, candidates=gate.rows, attempts=gate.attempts,
        complete_byte_cap=gate.cap, file_bytes=len(blob), budget_kbps=gate.budget_kbps,
        admissible_candidate_ids=[row['id'] for row in gate.rows if row['admissible']],
        payload_byte_identical=True, decoder_cost_measured=False, seconds=time.perf_counter()-started,
        scope='Finite existing-feature header grid; target cost and heldout benefit not established')
    save(gate.output/'report-private.json', report)
    write_pcm16_wav(gate.output/'decoded.wav', pwm_pcm16(pcm))
    return blob, pcm, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('incumbent', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--common', required=True, type=Path)
    parser.add_argument('--v5-only', required=True, type=Path)
    parser.add_argument('--level-policy', choices=('auto-quiet', 'preserve'), default='auto-quiet')
    args = parser.parse_args()
    reference, input_info = load_voice_wav(args.reference, args.level_policy)
    _, _, report = run(reference, args.incumbent.read_bytes(), args.output,
        BatchDecoder(args.common), BatchDecoder(args.v5_only))
    save(args.output/'input-private.json', input_info)
    print(json.dumps(dict(selected_id=report['selected_id'], changed=report['selected_differs_from_incumbent'],
                         seconds=report['seconds'])))


if __name__ == '__main__':
    main()
