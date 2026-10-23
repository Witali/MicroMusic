#!/usr/bin/env python3
"""Build the pinned fixed-point Xiph decoder without autotools or downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_profile

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/speex-1.2.1'
SOURCES = '''bits cb_search exc_10_16_table exc_10_32_table exc_20_32_table
exc_5_256_table exc_5_64_table exc_8_128_table filters gain_table gain_table_lbr
lpc lsp lsp_tables_nb ltp modes nb_celp quant_lsp speex speex_callbacks'''.split()
DEFINES = ['FIXED_POINT', 'DISABLE_ENCODER', 'DISABLE_WIDEBAND', 'DISABLE_VBR',
           'DISABLE_FLOAT_API', 'DISABLE_WARNINGS', 'DISABLE_NOTIFICATIONS',
           'RELEASE', 'EXPORT=']


def verify_sources():
    for directory, filename in [(VENDOR, 'UPSTREAM.json'),
                                (ROOT, 'handoff/import-manifest.json')]:
        for item in json.loads((directory / filename).read_text(encoding='utf-8'))['files']:
            data = (directory / item['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise RuntimeError('Source hash mismatch: ' + item['path'])


def run(args, cwd=None):
    subprocess.run([str(a) for a in args], check=True, cwd=cwd)


def prepare(variant):
    verify_sources()
    output = ROOT / 'build' / variant
    source = output / 'source'
    shutil.copytree(VENDOR, source, dirs_exist_ok=True)
    (source / 'include/speex/speex_config_types.h').write_text(
        '#include <stdint.h>\n'
        'typedef int16_t spx_int16_t;\ntypedef uint16_t spx_uint16_t;\n'
        'typedef int32_t spx_int32_t;\ntypedef uint32_t spx_uint32_t;\n', encoding='utf-8')
    if variant != 'reference':
        scripts = ROOT / 'handoff/upstream/tools'
        run([sys.executable, scripts / 'apply_upstream_port.py', source])
        run([sys.executable, scripts / 'apply_tight_exc.py', source])
    if variant == 'profile':
        apply_profile.apply(source)
    return output, source


def host(compiler, variant):
    output, source = prepare(variant)
    definitions = DEFINES.copy()
    if variant != 'reference':
        definitions.append('SPEEX_AVR_COMPACT_LSP')
    if variant in ('tight', 'profile'):
        definitions.append('SPEEX_AVR_TIGHT_EXC')
    if variant == 'profile':
        definitions.append('SPEEX_AVR_PROFILE')
    sources = SOURCES if variant != 'profile' else PROFILE_SOURCES
    executable = output / ('decode.exe' if os.name == 'nt' else 'decode')
    # Upstream ALIGN casts pointers to long only to examine low alignment bits;
    # Windows has 32-bit long even in a 64-bit process. Keep the oracle intact.
    run([compiler, '-O2', '-fwrapv', '-fno-strict-aliasing',
         '-Wno-pointer-to-int-cast', '-D_CRT_SECURE_NO_WARNINGS',
         *['-D' + d for d in definitions],
         '-I' + str(source / 'include'), '-I' + str(source / 'libspeex'),
         '-I' + str(ROOT / 'src'),
         *[source / 'libspeex' / (s + '.c') for s in sources],
         *([ROOT / 'src/speex_avr.c', ROOT / 'src/bits.c'] if variant == 'profile' else []),
         ROOT / 'tests/decode.c', '-o', executable,
         *([] if os.name == 'nt' else ['-lm'])])
    return executable


PROFILE_SOURCES = '''cb_search exc_10_32_table filters gain_table_lbr lsp
lsp_tables_nb ltp nb_celp quant_lsp'''.split()


def verify_primitives(compiler):
    output = ROOT / 'build/profile'
    reference = ROOT / 'build/reference/source'
    source = output / 'source'
    flags = ['-O2', '-fwrapv', '-fno-strict-aliasing', '-Wno-pointer-to-int-cast',
             *['-D' + d for d in DEFINES], '-I' + str(source / 'include'),
             '-I' + str(source / 'libspeex'), '-I' + str(ROOT / 'src')]
    obj = output / 'reference-lsp.o'
    run([compiler, *flags, '-Dlsp_to_lpc=reference_lsp', '-Dlsp_interpolate=reference_interpolate',
         '-c', reference / 'libspeex/lsp.c', '-o', obj])
    executable = output / ('primitives.exe' if os.name == 'nt' else 'primitives')
    run([compiler, *flags, '-DSPEEX_AVR_COMPACT_LSP', obj, source / 'libspeex/lsp.c',
         ROOT / 'src/bits.c', ROOT / 'tests/primitives.c', '-o', executable])
    run([executable])


def avr(compiler, packet_file=None, frame_load_cycles=0):
    if not 0 <= frame_load_cycles <= 320000 or (frame_load_cycles and packet_file is None):
        raise ValueError('Frame load requires a player stream and 0..320000 cycles')
    output, source = prepare('profile')
    definitions = DEFINES + ['SPEEX_AVR_COMPACT_LSP', 'SPEEX_AVR_TIGHT_EXC',
                             'SPEEX_AVR_PROFILE', 'SPEEX_AVR_FAST_MUL']
    name = 'speex-test'
    main = ROOT / 'tests/avr_decode.c'
    if packet_file is not None:
        data = packet_file.read_bytes()
        if not data or len(data) % 20 or len(data) > 32760 or any(data[i] >> 3 != 3 for i in range(0, len(data), 20)):
            raise ValueError('Expected complete 20-byte NB mode-3 packets fitting AVR Flash')
        output = ROOT / 'build/player'
        output.mkdir(parents=True, exist_ok=True)
        rows = [','.join(str(v) for v in data[i:i+20]) for i in range(0, len(data), 20)]
        (output / 'sample.h').write_text('#define SPEEX_SAMPLE_FRAMES ' + str(len(data)//20) +
            '\nstatic const uint8_t sample_data[] PROGMEM = {\n' + ',\n'.join(rows) + '\n};\n', encoding='utf-8')
        (output / 'input.json').write_text(json.dumps({'file': packet_file.name,
            'sha256': hashlib.sha256(data).hexdigest(), 'frames': len(data)//20,
            'frameLoadCycles': frame_load_cycles}, indent=2) + '\n', encoding='utf-8')
        name = 'speex-player'
        main = ROOT / 'src/player.c'
        definitions.append('SPEEX_AVR_OUTPUT_HOOK')
        if frame_load_cycles:
            definitions.append('SPEEX_AVR_FRAME_LOAD_CYCLES=' + str(frame_load_cycles))
    flags = ['-mmcu=atmega328p', '-O3', '-flto', '-fwrapv', '-fno-strict-aliasing',
             '-ffunction-sections', '-fdata-sections', '-fstack-usage',
             *['-D' + d for d in definitions],
             '-I' + str(source / 'include'), '-I' + str(source / 'libspeex'),
             '-I' + str(ROOT / 'src'), '-I' + str(output)]
    executable = output / (name + '.elf')
    run([compiler, *flags,
         *[source / 'libspeex' / (s + '.c') for s in PROFILE_SOURCES],
         ROOT / 'src/speex_avr.c', ROOT / 'src/bits.c', ROOT / 'src/lpc_update.S',
         ROOT / 'src/pitch_add.S', main,
         '-Wl,--gc-sections,-Map=' + str(output / (name + '.map')), '-o', executable], cwd=output)
    prefix = str(Path(compiler).with_name('avr-'))
    extension = '.exe' if str(compiler).endswith('.exe') else ''
    run([prefix + 'objcopy' + extension, '-O', 'ihex', '-R', '.eeprom', executable, output / (name + '.hex')])
    run([prefix + 'objcopy' + extension, '-O', 'binary', '-R', '.eeprom', executable, output / (name + '.bin')])
    run([prefix + 'size' + extension, '-C', '--mcu=atmega328p', executable])
    symbols = subprocess.check_output([prefix + 'nm' + extension, '-n', str(executable)], text=True)
    (output / 'symbols.txt').write_text(symbols, encoding='utf-8')
    return executable


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC', 'clang'))
    parser.add_argument('--variant', choices=['reference', 'compact', 'tight', 'profile'], default='reference')
    parser.add_argument('--avr-gcc', help='Build the ATmega328P validation firmware instead of the host decoder')
    parser.add_argument('--player', type=Path, help='Embed this NB3 raw stream and build the PWM player (requires --avr-gcc)')
    parser.add_argument('--frame-load-cycles', type=int, default=0,
                        help='Inject this many extra CPU cycles per player frame to verify headroom (test only)')
    args = parser.parse_args()
    if args.player and not args.avr_gcc:
        parser.error('--player requires --avr-gcc')
    if args.frame_load_cycles and not (args.player and args.avr_gcc):
        parser.error('--frame-load-cycles requires --player and --avr-gcc')
    print(avr(args.avr_gcc, args.player, args.frame_load_cycles) if args.avr_gcc else host(args.cc, args.variant))
