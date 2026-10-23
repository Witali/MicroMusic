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


def run(args):
    subprocess.run([str(a) for a in args], check=True)


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
    return output, source


def host(compiler, variant):
    output, source = prepare(variant)
    definitions = DEFINES.copy()
    if variant != 'reference':
        definitions.append('SPEEX_AVR_COMPACT_LSP')
    if variant == 'tight':
        definitions.append('SPEEX_AVR_TIGHT_EXC')
    executable = output / ('decode.exe' if os.name == 'nt' else 'decode')
    # Upstream ALIGN casts pointers to long only to examine low alignment bits;
    # Windows has 32-bit long even in a 64-bit process. Keep the oracle intact.
    run([compiler, '-O2', '-fwrapv', '-fno-strict-aliasing',
         '-Wno-pointer-to-int-cast', '-D_CRT_SECURE_NO_WARNINGS',
         *['-D' + d for d in definitions],
         '-I' + str(source / 'include'), '-I' + str(source / 'libspeex'),
         *[source / 'libspeex' / (s + '.c') for s in SOURCES],
         ROOT / 'tests/decode.c', '-o', executable,
         *([] if os.name == 'nt' else ['-lm'])])
    return executable


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC', 'clang'))
    parser.add_argument('--variant', choices=['reference', 'compact', 'tight'], default='reference')
    args = parser.parse_args()
    print(host(args.cc, args.variant))
