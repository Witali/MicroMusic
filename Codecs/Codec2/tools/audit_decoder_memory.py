#!/usr/bin/env python3
"""Link the current full decoder against physical memory from AVR device headers.

The older AVR linker scripts use a generic data-region length unless explicitly
bounded. Static linking is a necessary check; stack/IRQ admission is separate.
"""
import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_frontend as front

ROOT = front.ROOT
SOURCE = front.VENDOR / 'src'
BUILD = ROOT.parents[1] / 'build/codec2/memory'


def device_memory(compiler, mcu):
    macros = front.run([compiler, '-mmcu=' + mcu, '-dM', '-E', '-include', 'avr/io.h', '-'],
                       input='', capture_output=True, text=True).stdout
    result = {}
    for line in macros.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in ('RAMSTART', 'RAMEND', 'FLASHEND'):
            result[parts[1]] = int(parts[2].strip('()'), 0)
    assert len(result) == 3
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-gcc', default='avr-gcc')
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    report = {'verified_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'Physical static link bounds only. Success is not proof of stack, real-time, IRQ or board operation.',
              'compiler': front.run([args.avr_gcc, '--version'], capture_output=True, text=True).stdout.splitlines()[0],
              'results': []}
    for mcu in ('atmega64a', 'atmega1284p'):
        output = BUILD / mcu
        output.mkdir(exist_ok=True)
        memory = device_memory(args.avr_gcc, mcu)
        sram = memory['RAMEND'] - memory['RAMSTART'] + 1
        flash = memory['FLASHEND'] + 1
        command = [args.avr_gcc, '-mmcu=' + mcu, '-Os', '-std=c99', '-fstack-usage', '-fno-strict-aliasing',
            '-ffunction-sections', '-fdata-sections', '-I' + str(ROOT / 'include'), '-I' + str(SOURCE),
            ROOT / 'src/decoder_float.c', ROOT / 'src/parameters.c', SOURCE / 'lsp.c',
            SOURCE / 'kiss_fft.c', SOURCE / 'kiss_fftr.c', ROOT / 'tests/avr_decoder.c',
            '-Wl,--gc-sections,-Map=' + str(output / 'decoder.map'),
            '-Wl,--defsym=__DATA_REGION_ORIGIN__=' + str(0x800000 + memory['RAMSTART']),
            '-Wl,--defsym=__DATA_REGION_LENGTH__=' + str(sram),
            '-Wl,--defsym=__TEXT_REGION_LENGTH__=' + str(flash), '-o', output / 'decoder.elf', '-lm']
        outcome = subprocess.run([str(x) for x in command], cwd=output, capture_output=True, text=True)
        item = {'mcu': mcu, 'manufacturer_header_macros': memory, 'physical_flash_bytes': flash,
                'physical_sram_bytes': sram, 'static_link_passed': outcome.returncode == 0,
                'link_exit_code': outcome.returncode, 'link_diagnostics': outcome.stderr.strip()}
        mapping = (output / 'decoder.map').read_text(encoding='utf-8')
        sections = {}
        for section in ('.text', '.data', '.bss'):
            match = re.search(r'^' + re.escape(section) + r'\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)', mapping, re.M)
            assert match, section
            sections[section] = {'address': int(match[1], 16), 'bytes': int(match[2], 16)}
        item['map_sections'] = sections
        item['static_sram_bytes'] = sections['.data']['bytes'] + sections['.bss']['bytes']
        item['flash_bytes_including_data_initializer'] = sections['.text']['bytes'] + sections['.data']['bytes']
        item['static_sram_overflow_bytes'] = max(0, item['static_sram_bytes'] - sram)
        if outcome.returncode == 0:
            prefix = args.avr_gcc[:-3] if args.avr_gcc.endswith('gcc') else args.avr_gcc.replace('gcc.exe', '')
            item['section_sizes'] = front.run([prefix + 'size', '-A', output / 'decoder.elf'], capture_output=True, text=True).stdout
        report['results'].append(item)
        print(json.dumps(item), flush=True)
    report['sources'] = {name: front.digest(ROOT / name) for name in
        ('tools/audit_decoder_memory.py', 'include/codec2_decoder.h', 'src/decoder_float.c',
         'src/parameters.c', 'tests/avr_decoder.c', 'vendor/codec2-1.2.0/UPSTREAM.json')}
    front.dump(BUILD / 'audit.json', report)
    if args.record:
        (ROOT / 'reports').mkdir(exist_ok=True)
        front.dump(ROOT / 'reports/decoder-memory.json', report)


if __name__ == '__main__':
    main()
