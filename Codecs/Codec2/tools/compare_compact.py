#!/usr/bin/env python3
"""Compare complete AVR qualification against the first 4-KB compact checkpoint."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '00ae2c315f10d4ef0d006dcefb61d37ba46f86d2'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    original = subprocess.run(['git', 'show', BASELINE + ':Codecs/Codec2/reports/compact-decoder.json'],
                              cwd=ROOT, check=True, capture_output=True).stdout
    baseline = json.loads(original)
    current_path = ROOT / 'reports/compact-decoder.json'
    current = json.loads(current_path.read_text())
    assert baseline['avr_execution']['complete'] and current['avr_execution']['complete']
    assert baseline['avr_build']['compiler'] == current['avr_build']['compiler']
    assert baseline['avr_build']['manufacturer_header_memory'] == current['avr_build']['manufacturer_header_memory']
    assert baseline['sources']['tools/verify_compact.py'] == current['sources']['tools/verify_compact.py']
    assert len(baseline['avr_execution']['results']) == len(current['avr_execution']['results']) == 2
    for path, wanted in current['sources'].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == wanted, path
    streams = []
    for before, after in zip(baseline['avr_execution']['results'], current['avr_execution']['results']):
        for key in ['name', 'frames', 'samples', 'packetSha256', 'expectedSha256', 'outputSha256']:
            assert before[key] == after[key], key
        assert before['completeStream'] and after['completeStream']
        pairs = list(zip(before['perFrameCycles'], after['perFrameCycles']))
        assert len(pairs) == before['frames']
        assert all(new < old for old, new in pairs), 'A measured frame regressed'
        assert not before['includesInterrupts'] and not after['includesInterrupts']
        def resources(record):
            return {key: record[key] for key in ['flashBytes', 'staticSramBytes', 'stackBytes', 'freeSramAtPeak', 'maximumCycles', 'meanCycles']}
        streams.append({'name': after['name'], 'frames': after['frames'], 'pcm_unchanged': True,
            'before': resources(before), 'after': resources(after),
            'mean_cycle_reduction_percent': 100 * (1 - after['meanCycles'] / before['meanCycles']),
            'minimum_per_frame_reduction_percent': min(100 * (1 - new / old) for old, new in pairs),
            'maximum_per_frame_reduction_percent': max(100 * (1 - new / old) for old, new in pairs)})
    report = {'baseline_revision': BASELINE, 'baseline_report_sha256': hashlib.sha256(original).hexdigest(),
        'current_verification': 'compact-decoder.json', 'current_report_sha256': hashlib.sha256(current_path.read_bytes()).hexdigest(),
        'comparison_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'streams': streams, 'scope': 'Same ATmega64A/AVR-GCC settings, complete archived streams; identical AVR PCM. No active IRQ or real-time admission.'}
    destination = ROOT / 'reports/compact-pruning.json' if args.record else ROOT.parents[1] / 'build/codec2/compact/comparison.json'
    destination.write_bytes((json.dumps(report, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
