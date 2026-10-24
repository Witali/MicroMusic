"""Exercise zero-gain workspace reuse across subframes and frame boundaries.

All 16 zero/nonzero masks and 16 subframe-energy masks run in four phases.
Changing LSPs overwrite the shared arena between frames; repeated LSPs also
exercise the cached path. Expected PCM comes from unmodified Xiph 1.2.1.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', default='node')
    parser.add_argument('--firmware', type=Path)
    parser.add_argument('--backend', choices=['asm', 'c'])
    parser.add_argument('--out', type=Path, default=build.ROOT / 'build/zero-pitch-cases')
    parser.add_argument('--generate-only', action='store_true')
    args = parser.parse_args()
    streams, oracle = args.out / 'streams', args.out / 'oracle'
    streams.mkdir(parents=True, exist_ok=True)
    oracle.mkdir(parents=True, exist_ok=True)
    data = bytearray()
    coverage = set()
    seed = 0x5e87004f

    def random_bits(n):
        nonlocal seed
        seed ^= seed << 13; seed &= 0xffffffff
        seed ^= seed >> 17
        seed ^= seed << 5; seed &= 0xffffffff
        return seed & ((1 << n) - 1)

    for phase in range(4):
        for energy_mask in range(16):
            lsp = [random_bits(6) for _ in range(3)]
            for ordinal in range(16):
                # Reverse every other group: both zero -> nonzero and nonzero
                # -> zero transitions occur between frames, at every position.
                mask = ordinal if energy_mask & 1 else 15 - ordinal
                if not phase & 1:
                    lsp = [random_bits(6) for _ in range(3)]
                fields = [(0, 1), (3, 4)] + [(value, 6) for value in lsp]
                fields.append(((phase * 8 + energy_mask) % 32, 5))
                for sub in range(4):
                    pitch = (len(data) // 20 * 11 + sub * 37) % 128
                    gain = 0 if mask & (1 << sub) else 1 + random_bits(5) % 31
                    fields += [(pitch, 7), (gain, 5), ((energy_mask >> sub) & 1, 1)]
                    fields += [(random_bits(5), 5) for _ in range(4)]
                assert sum(n for _, n in fields) == 160
                packed = 0
                for value, n in fields:
                    assert 0 <= value < 1 << n
                    packed = (packed << n) | value
                data += packed.to_bytes(20, 'big')
                coverage.add((phase, mask, energy_mask))
    assert len(coverage) == 1024
    raw = streams / 'zero_gain_transitions.spxraw'
    raw.write_bytes(data)
    reference = build.ROOT / 'build/reference/decode.exe'
    if sys.platform != 'win32':
        reference = reference.with_suffix('')
    subprocess.run([reference, raw, oracle / 'zero_gain_transitions.pcm'], check=True)
    metadata = {'frames': 1024, 'zeroMasks': 16, 'energyMasks': 16,
                'phases': 4, 'changingAndRepeatedLsp': True, 'seed': '0x5e87004f'}
    (args.out / 'coverage.json').write_text(json.dumps(metadata, indent=2) + '\n')
    if not args.generate_only:
        command = [args.node, build.ROOT / 'tests/verify_avr.mjs', '--streams', streams,
                   '--oracle', oracle, '--out', args.out, '--verify-reset']
        if args.firmware:
            command += ['--firmware', args.firmware]
        if args.backend:
            command += ['--backend', args.backend]
        subprocess.run(command, check=True)
        report_path = args.out / 'avr-verification.json'
        report = json.loads(report_path.read_text())
        report['coverage'] = metadata
        report_path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
