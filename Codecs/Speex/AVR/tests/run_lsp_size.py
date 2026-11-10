#!/usr/bin/env python3
"""Copy frozen scalar fixtures to a fresh ignored output, then test both orders."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', required=True)
    parser.add_argument('--node', required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/lsp-size-reproduce')
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--adopt', type=Path, help='Reuse full reports only after complete fixture/verifier identity')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to((ROOT / 'build').resolve()):
        raise ValueError('Fixture output must remain under the codec build directory')
    # A fresh directory protects preserved evidence from accidental overwrites.
    shutil.copytree(ROOT / 'tests/lsp-size', out)
    environment = dict(os.environ, AVR8JS_PACKAGE=str(ROOT / 'package.json'))
    rows = []
    for variant, backend in [('loop', 'asm'), ('inline', 'asm'), ('loop', 'c'), ('loop', 'generic')]:
        subprocess.run([sys.executable, out / 'build.py', '--avr-gcc', args.avr_gcc,
                        '--variant', variant, '--backend', backend], check=True)
        for order in [8, 10]:
            label = f'{variant}{order}-{backend}'
            folder = out / label
            quick = args.quick or backend != 'asm'
            report_name = 'verification-' + ('quick' if quick else 'full') + '-irq.json'
            if args.adopt:
                reference = args.adopt / label
                assert (reference / 'unit.bin').read_bytes() == (folder / 'unit.bin').read_bytes()
                for filename in [f'verify{order}.mjs', 'avr_tick.mjs']:
                    assert (args.adopt / filename).read_bytes() == (out / filename).read_bytes()
                old, new = [json.loads((p / 'input.json').read_text()) for p in [reference, folder]]
                assert old['sourceSha256'] == new['sourceSha256']
                shutil.copyfile(reference / report_name, folder / report_name)
            else:
                subprocess.run([args.node, out / f'verify{order}.mjs', folder, '--irq',
                                *(['--quick'] if quick else [])], env=environment, check=True)
            report = json.loads((folder / report_name).read_text())
            assert report['binarySha256'] == hashlib.sha256((folder / 'unit.bin').read_bytes()).hexdigest()
            assert report['independentSequentialBigIntExact'] and report['originalSequentialAndPairedCExact']
            assert report['noLostTimerInterrupts'] and report['includesInterrupts']
            assert report['cases'] == ({8: 796, 10: 966} if quick else {8: 41984, 10: 50688})[order]
            assert report['timerEvents'] == report['completedTimerInterrupts'] > 0
            assert report['verifierSha256'] == hashlib.sha256((out / f'verify{order}.mjs').read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            assert report['sourceSha256'] == json.loads((folder / 'input.json').read_text())['sourceSha256']
            rows.append(dict(fixture=label, cases=report['cases'], binarySha256=report['binarySha256'],
                             adoptedIdenticalEvidence=bool(args.adopt)))
    (out / 'reproduction.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8')
    print('PASS both LSP orders, explicit C/generic controls and timer IRQs; no decoder executed')


if __name__ == '__main__':
    main()
