#!/usr/bin/env python3
"""Add a *conditional*, separately testable compact LSP function to Xiph Speex.

The original fixed-point function remains available with
SPEEX_AVR_COMPACT_LSP undefined. No altered files in the baseline R4 archive.
"""
from pathlib import Path
import argparse
import re

ROOT = Path(__file__).resolve().parents[1]
START = '/* SPEEX_AVR_COMPACT_LSP_BEGIN */'
END = '/* SPEEX_AVR_COMPACT_LSP_END */'

def patch(source: Path) -> None:
    f = source / 'libspeex' / 'lsp.c'
    if not f.exists():
        raise SystemExit(f'No Xiph Speex source: {f}')
    raw = f.read_text()
    if START in raw:
        print('Already patched:', f)
        patch_fastmul(source)
        patch_avr_types(source)
        return
    # In official 1.2.1, fixed and float lsp_to_lpc implementations are
    # separated by #ifdef FIXED_POINT and #else below the encoder routines.
    pat = re.compile(r'((?:^|\n)#ifdef FIXED_POINT\s*\n)(void lsp_to_lpc\s*\([^\n]+\).*?\n\})(\s*\n#else\s*\n\s*void lsp_to_lpc\s*\()', re.S)
    m = pat.search(raw)
    if not m:
        raise SystemExit('Original fixed-point lsp_to_lpc not found; source changed. No modifications made.')
    compact = (ROOT / 'patches' / 'compact_lsp_function.c.inc').read_text()
    old = m.group(2)
    new = (m.group(1) + START + '\n#if defined(SPEEX_AVR_COMPACT_LSP)\n' + compact
           + '\n#else\n' + old + '\n#endif /* SPEEX_AVR_COMPACT_LSP */\n'
           + END + m.group(3))
    f.write_text(raw[:m.start()] + new + raw[m.end():])
    print('Patched:', f, 'Original function retained under #else')
    patch_fastmul(source)
    patch_avr_types(source)


def patch_fastmul(source: Path) -> None:
    arch = source / 'libspeex' / 'arch.h'
    raw = arch.read_text()
    mark = '#ifdef SPEEX_AVR_FAST_MUL\n#include "avr_fastmul.h"\n#endif\n'
    if mark not in raw:
        needle = '#include "fixed_generic.h"'
        if needle not in raw:
            raise SystemExit('fixed_generic.h include not found; will not patch arch.h')
        raw = raw.replace(needle, needle + '\n\n' + mark, 1)
        arch.write_text(raw)
    dst = source / 'libspeex' / 'avr_fastmul.h'
    dst.write_bytes((ROOT / 'patches' / 'avr_fastmul.h').read_bytes())
    print('Installed optional AVR201 fastmul:', dst)


def patch_avr_types(source: Path) -> None:
    f = source / 'include' / 'speex' / 'speex_types.h'
    raw = f.read_text()
    mark = '#elif defined(__AVR__) /* 16-bit int ABI: use exact-width integer types */'
    if mark in raw:
        print('AVR type specialization already installed:', f)
        return
    needle = '#include "speex_config_types.h"'
    if raw.count(needle) != 1:
        raise SystemExit('Cannot find unambiguous Speex generated-types include')
    insertion = (mark + '\n# include <stdint.h>\n'
                 'typedef int16_t  spx_int16_t;\n'
                 'typedef uint16_t spx_uint16_t;\n'
                 'typedef int32_t  spx_int32_t;\n'
                 'typedef uint32_t spx_uint32_t;\n\n#else\n\n')
    # Existing preprocessor branch ends with #else; replace it with __AVR__
    # specialized branch followed by the original, unchanged fallback.
    needle2 = '#else\n\n' + needle
    if raw.count(needle2)!=1:
        raise SystemExit('Cannot locate final types fallback branch')
    raw=raw.replace(needle2,insertion+needle,1)
    f.write_text(raw)
    print('Installed exact-width AVR types:', f)

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('speex_source_root', type=Path)
    patch(ap.parse_args().speex_source_root)
