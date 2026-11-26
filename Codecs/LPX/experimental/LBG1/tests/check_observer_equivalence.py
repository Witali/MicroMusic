"""Replay existing complete ELFs with original and diagnostic observers.

No firmware rebuild or production edits. The only observer adaptation adds
valid-only PWM output for slow Tiny controls; every original timing field and
the complete PWM stream must remain identical on the same linked ELF.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ORIGINAL = REPO / 'Codecs/LPX/validation/attiny88/sim_player.c'


def run(*args):
    result = subprocess.run(list(map(str, args)), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--case', default='chego-p4')
    args = parser.parse_args()
    base = args.run.resolve()
    if (REPO / 'build').resolve() not in base.parents:
        raise ValueError('Use a generated run under ignored build/')
    output = base / 'observer-equivalence'
    output.mkdir()
    rows = []
    for target in ('attiny88', 'atmega328p'):
        case = base / args.case / 'baseline' / target / 'asm'
        observer = output / target
        run('gcc', '-O2', '-std=c11', '-I' + str(case), '-I/usr/include/simavr',
            ORIGINAL, '-lsimavr', '-lelf', '-o', observer)
        pwm, timing = output / (target + '.pwm'), output / (target + '.json')
        run(observer, case / 'player.elf', pwm, timing)
        original = json.loads(timing.read_text())
        adapted = json.loads((case / 'timing.json').read_text())
        if original != adapted or pwm.read_bytes() != (case / 'actual.pwm').read_bytes():
            raise AssertionError('Observer change altered a measured result')
        rows.append(dict(target=target, elf_sha256=sha(case / 'player.elf'),
                         complete_pwm_sha256=sha(pwm), all_original_timing_fields_equal=True,
                         complete_pwm_equal=True, timing_field_count=len(original)))
    result = dict(schema='lbg1-original-observer-equivalence-v1',
                  original_observer_sha256=sha(ORIGINAL),
                  diagnostic_observer_sha256=sha(base / 'observer-valid.c'),
                  rows=rows, firmware_rebuilt=False)
    (output / 'proof.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
