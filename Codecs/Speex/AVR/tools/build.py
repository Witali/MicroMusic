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


def host(compiler, variant, enable_nb4=False):
    output, source = prepare(variant)
    definitions = DEFINES.copy()
    if variant != 'reference':
        definitions.append('SPEEX_AVR_COMPACT_LSP')
    if variant in ('tight', 'profile'):
        definitions.append('SPEEX_AVR_TIGHT_EXC')
    if variant == 'profile':
        definitions.append('SPEEX_AVR_PROFILE')
        definitions.append('SPEEX_ENABLE_NB4='+str(int(enable_nb4)))
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


PROFILE_SOURCES = '''cb_search exc_10_32_table exc_8_128_table filters gain_table_lbr lsp
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
         source / 'libspeex/quant_lsp.c',source / 'libspeex/lsp_tables_nb.c',
         ROOT / 'src/bits.c', ROOT / 'tests/primitives.c', '-o', executable])
    run([executable])
    executable = output / ('iir-direct.exe' if os.name == 'nt' else 'iir-direct')
    run([compiler, *flags, ROOT / 'tests/iir_direct.c', '-o', executable])
    run([executable])


ASM_SOURCES = ['lpc_dot.S', 'pitch_add.S', 'innovation.S', 'q14.S', 'lsp_advance.S', 'lsp_finish.S', 'lsp_stage.S', 'lsp_pair.S', 'lsp_first.S']


def export_c(destination, enable_nb4=False):
    """Export a self-contained C library, without a test main or AVR player."""
    destination = destination.resolve()
    # Never merge generated files into user source directories or an older
    # package: every export gets a fresh reviewable directory, without deletes.
    if destination.exists():
        raise ValueError('Export destination must not exist: ' + str(destination))
    _, source = prepare('profile')
    destination.mkdir(parents=True)
    shutil.copytree(source / 'include', destination / 'include')
    private = destination / 'src'
    private.mkdir()
    for path in (source / 'libspeex').glob('*.h'):
        shutil.copyfile(path, private / path.name)
    for path in (ROOT / 'src').iterdir():
        if path.suffix == '.h' or path.name.endswith('.c.inc') or path.name == 'short_pitch_kernel.inc':
            shutil.copyfile(path, private / path.name)
    for name in ['speex_nb.h', 'speex_nb3.h', 'speex_avr.h']:
        shutil.copyfile(ROOT / 'src' / name, destination / 'include' / name)
    sources = []
    for name in PROFILE_SOURCES:
        shutil.copyfile(source / 'libspeex' / (name + '.c'), private / (name + '.c'))
        sources.append('src/' + name + '.c')
    for name in ['speex_avr.c', 'bits.c']:
        shutil.copyfile(ROOT / 'src' / name, private / name)
        sources.append('src/' + name)
    definitions = DEFINES + ['SPEEX_AVR_COMPACT_LSP', 'SPEEX_AVR_TIGHT_EXC',
        'SPEEX_AVR_PROFILE', 'SPEEX_NB3_ENABLE_ASM=0', 'SPEEX_NB3_CHECK_SCRATCH=0']
    if enable_nb4:definitions.append('SPEEX_ENABLE_NB4=1')
    (destination / 'sources.json').write_text(json.dumps({'backend': 'c',
        'cStandard': 'c11', 'sources': sources, 'includeDirectories': ['include', 'src'],
        'definitions': definitions,
        'gccClangFlags': ['-fwrapv', '-fno-strict-aliasing', '-ffunction-sections', '-fdata-sections']
        }, indent=2) + '\n', encoding='utf-8')
    shutil.copyfile(ROOT / 'tools/portable-CMakeLists.txt', destination / 'CMakeLists.txt')
    if enable_nb4:
        with (destination/'CMakeLists.txt').open('a',encoding='utf-8') as f:f.write('\ntarget_compile_definitions(speex_nb3 PUBLIC SPEEX_ENABLE_NB4=1)\n')
    shutil.copyfile(VENDOR / 'COPYING', destination / 'COPYING')
    shutil.copyfile(ROOT / 'PORTING.md', destination / 'PORTING.md')
    manifest = {p.relative_to(destination).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination / 'SHA256.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return destination


def avr(compiler, packet_file=None, frame_load_cycles=0, backend='c', packet_bytes=None, enable_nb4=None):
    if backend not in ('asm', 'c'):
        raise ValueError('Unknown arithmetic backend: ' + backend)
    if packet_bytes not in (None,20,28):
        raise ValueError('NB test packet width must be 20 or 28 bytes')
    width=packet_bytes or 20
    if not 0 <= frame_load_cycles <= 320000 or (frame_load_cycles and packet_file is None):
        raise ValueError('Frame load requires a player stream and 0..320000 cycles')
    output, source = prepare('profile')
    definitions = DEFINES + ['SPEEX_AVR_COMPACT_LSP', 'SPEEX_AVR_TIGHT_EXC',
                             'SPEEX_AVR_PROFILE', 'SPEEX_AVR_FAST_MUL',
                             'SPEEX_NB3_ENABLE_ASM=' + str(int(backend == 'asm'))]
    name = 'speex-test'
    main = ROOT / 'tests/avr_decode.c'
    if packet_file is not None:
        data = packet_file.read_bytes()
        mode=data[0]>>3 if data else -1
        detected={3:20,4:28}.get(mode,0)
        if not detected or (packet_bytes is not None and detected!=packet_bytes) or len(data)%detected or len(data)>32760 or any(data[i]>>3!=mode for i in range(0,len(data),detected)):
            raise ValueError('Expected uniform raw NB3/20-byte or NB4/28-byte packets fitting AVR Flash')
        width=detected
        output = ROOT / 'build/player'
        output.mkdir(parents=True, exist_ok=True)
        rows = [','.join(str(v) for v in data[i:i+width]) for i in range(0, len(data), width)]
        (output / 'sample.h').write_text('#define SPEEX_SAMPLE_PACKET_BYTES '+str(width)+'\n#define SPEEX_SAMPLE_FRAMES ' + str(len(data)//width) +
            '\nstatic const uint8_t sample_data[] PROGMEM = {\n' + ',\n'.join(rows) + '\n};\n', encoding='utf-8')
        (output / 'input.json').write_text(json.dumps({'file': packet_file.name,
            'sha256': hashlib.sha256(data).hexdigest(), 'frames': len(data)//width,'packetBytes':width,
            'frameLoadCycles': frame_load_cycles}, indent=2) + '\n', encoding='utf-8')
        name = 'speex-player'
        main = ROOT / 'src/player.c'
        definitions.append('SPEEX_AVR_OUTPUT_HOOK')
        if frame_load_cycles:
            definitions.append('SPEEX_AVR_FRAME_LOAD_CYCLES=' + str(frame_load_cycles))
    enabled=width==28 if enable_nb4 is None else bool(enable_nb4)
    if width==28 and not enabled:raise ValueError('28-byte packets require the NB4 feature')
    definitions+=['SPEEX_TEST_PACKET_BYTES='+str(width),'SPEEX_ENABLE_NB4='+str(int(enabled))]
    # Share repeated register saves/restores; shorten in-range calls and jumps.
    flags = ['-std=c11', '-mmcu=atmega328p', '-mcall-prologues', '-mrelax',
             '-Os', '-flto', '-fwrapv', '-fno-strict-aliasing',
             '-ffunction-sections', '-fdata-sections', '-fstack-usage',
             *['-D' + d for d in definitions],
             '-I' + str(source / 'include'), '-I' + str(source / 'libspeex'),
             '-I' + str(ROOT / 'src'), '-I' + str(output)]
    executable = output / (name + '.elf')
    run([compiler, *flags,
         *[source / 'libspeex' / (s + '.c') for s in PROFILE_SOURCES],
         ROOT / 'src/speex_avr.c', ROOT / 'src/bits.c',
         *([ROOT / 'src' / s for s in ASM_SOURCES] if backend == 'asm' else []), main,
         '-Wl,--gc-sections,-Map=' + str(output / (name + '.map')), '-o', executable], cwd=output)
    prefix = str(Path(compiler).with_name('avr-'))
    extension = '.exe' if str(compiler).endswith('.exe') else ''
    run([prefix + 'objcopy' + extension, '-O', 'ihex', '-R', '.eeprom', executable, output / (name + '.hex')])
    run([prefix + 'objcopy' + extension, '-O', 'binary', '-R', '.eeprom', executable, output / (name + '.bin')])
    run([prefix + 'size' + extension, '-C', '--mcu=atmega328p', executable])
    symbols = subprocess.check_output([prefix + 'nm' + extension, '-n', str(executable)], text=True)
    (output / 'symbols.txt').write_text(symbols, encoding='utf-8')
    (output / 'backend.json').write_text(json.dumps({'backend': backend,'packetBytes':width,'nb4Enabled':enabled,
        'handwrittenAssembly': backend == 'asm',
        'binarySha256': hashlib.sha256((output / (name + '.bin')).read_bytes()).hexdigest()
        }, indent=2) + '\n', encoding='utf-8')
    return executable


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC', 'clang'))
    parser.add_argument('--variant', choices=['reference', 'compact', 'tight', 'profile'], default='reference')
    parser.add_argument('--avr-gcc', help='Build the ATmega328P validation firmware instead of the host decoder')
    parser.add_argument('--backend', choices=['asm', 'c'], default=None,
                        help='AVR arithmetic backend (default c); asm explicitly enables AVR assembly')
    parser.add_argument('--export-c', type=Path,
                        help='Export a self-contained portable C/CMake library to a new directory')
    parser.add_argument('--player', type=Path, help='Embed a uniform NB3/NB4 raw stream and build the PWM player (requires --avr-gcc)')
    parser.add_argument('--packet-bytes',type=int,choices=[20,28],help='Bare AVR mailbox width; player width is inferred')
    parser.add_argument('--enable-nb4',action='store_true',default=None,help='Enable NB 11 kbit/s (automatic for 28-byte AVR input)')
    parser.add_argument('--frame-load-cycles', type=int, default=0,
                        help='Inject this many extra CPU cycles per player frame to verify headroom (test only)')
    args = parser.parse_args()
    if args.export_c:
        if args.avr_gcc or args.player or args.frame_load_cycles or args.backend == 'asm':
            parser.error('--export-c creates a C library and cannot build AVR firmware')
        print(export_c(args.export_c,bool(args.enable_nb4)))
        sys.exit(0)
    if args.player and not args.avr_gcc:
        parser.error('--player requires --avr-gcc')
    if args.frame_load_cycles and not (args.player and args.avr_gcc):
        parser.error('--frame-load-cycles requires --player and --avr-gcc')
    if args.backend == 'asm' and not args.avr_gcc:
        parser.error('The asm backend requires --avr-gcc')
    print(avr(args.avr_gcc, args.player, args.frame_load_cycles, args.backend or 'c',args.packet_bytes,args.enable_nb4)
          if args.avr_gcc else host(args.cc, args.variant,bool(args.enable_nb4)))
