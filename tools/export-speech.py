#!/usr/bin/env python3
"""Export trained speech for PC, AVR or a generic microcontroller."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ATtiny13A/Sound/codec'))
from speech_targets import export_model, resolve_profile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--target', choices=('pc', 'avr', 'mcu'), default='pc')
    parser.add_argument('--arithmetic', choices=('float', 'fixed'))
    parser.add_argument('--mcu', help='attiny13 for AVR; descriptive chip name for generic MCU')
    parser.add_argument('--profile', type=Path, help='speech-output-profile-v1 JSON with memory/CPU limits')
    parser.add_argument('--symbol', default='speech_data', help='C data array identifier')
    parser.add_argument('--build', action='store_true', help='invoke the profile firmware adapter')
    parser.add_argument('--avr-bin', type=Path, help='optional toolchain path passed to the AVR adapter')
    parser.add_argument('--node', type=Path, help='optional emulator runtime passed to the AVR adapter')
    args = parser.parse_args()
    if (args.avr_bin or args.node) and not args.build:
        parser.error('--avr-bin/--node require --build')
    try:
        profile = resolve_profile(args.target, args.arithmetic, args.mcu, args.profile)
        model = json.loads(args.model.read_text(encoding='utf-8'))
        adapter_options = []
        for flag, value in (('--avr-bin', args.avr_bin), ('--node', args.node)):
            if value:
                adapter_options += [flag, str(value)]
        manifest = export_model(model, args.output, profile, build=args.build,
                                adapter_options=adapter_options, symbol=args.symbol)
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        parser.exit(2, str(error)+'\n')
    print(json.dumps(dict(profile=profile.name, data_bytes=manifest['data_bytes'],
                         validation=manifest['validation'], output=str(args.output)), indent=2))


if __name__ == '__main__':
    main()
