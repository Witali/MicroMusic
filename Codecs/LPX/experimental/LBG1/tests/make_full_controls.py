"""Create genuine LG partial/reset/curve inputs for the full AVR player.

Only generated files under ignored build/ are written. Partial controls use
a legal reset-zero LPC anchor, scale zero and mandatory P4 pulse packets.
They test parser tails, not speech quality or representative CPU load.
"""
from pathlib import Path
import argparse
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'avr'))
import run_full as full


class Bits:
    def __init__(self):
        self.output, self.at = bytearray(), 0

    def put(self, value, count):
        for i in range(count):
            if not self.at % 8:
                self.output.append(0)
            self.output[-1] |= ((value >> i) & 1) << (self.at % 8)
            self.at += 1


def silence(samples):
    writer = Bits()
    for frame in range((samples + 319) // 320):
        writer.put(int(frame == 0), 1)
        if frame == 0:
            writer.put(0, 1)  # Anchor equals the reset-zero base.
        for half in range(2):
            start = frame * 320 + half * 160
            if start >= samples:
                break
            writer.put(0, 7)  # Literal scale, index zero.
            writer.put(0, 5)  # Literal pitch, gain zero, no lag.
            for group in range(4):
                if start + group * 40 < samples:
                    writer.put(0, 10)  # Two mandatory P4 positions/signs.
    return struct.pack('<2sBHHHHH', b'LG', 4, 8000, samples, 0, 0, len(writer.output)) + writer.output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = full.safe_build(args.output)
    output.mkdir(parents=True)
    cases = []
    for samples in (1, 41, 321):
        data = output / f'partial-{samples}.lg1'
        pcm = output / f'partial-{samples}.pcm'
        data.write_bytes(silence(samples))
        pcm.write_bytes(bytes(samples * 2))
        cases.append(dict(name=f'partial-{samples}', path=data.relative_to(full.REPO).as_posix(),
                          pcm=pcm.relative_to(full.REPO).as_posix(), backends=['asm', 'c']))
    exact = Path('build/lbg1-encoder/chego-p4/exact.lbg')
    pcm = Path('build/lbg1-encoder/chego-p4/exact.pcm')
    cases.append(dict(name='reset-exact', path=exact.as_posix(), pcm=pcm.as_posix(), repeat=2, backends=['asm', 'c']))
    cases.append(dict(name='forced-generic-exact', path=exact.as_posix(), pcm=pcm.as_posix(), backends=['generic']))
    cases.append(dict(name='true-log-and-pitch-curves', path='build/lbg1-encoder/synthetic-log-rise.lbg',
                      pcm='build/lbg1-encoder/synthetic-log-rise.pcm', backends=['asm', 'c']))
    manifest = dict(schema='lbg1-full-avr-control-inputs-v1', cases=cases,
                    method='Full valid LG files: partial1/41/321, genuine speech reset repeated twice, forced-generic architecture override, and actual true-log-Q8 plus linear-lag commands.')
    full.write_json(output / 'manifest.json', manifest)
    print(output / 'manifest.json')


if __name__ == '__main__':
    main()
