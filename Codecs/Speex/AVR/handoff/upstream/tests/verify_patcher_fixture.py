#!/usr/bin/env python3
"""Check upstream patcher on a fixture retaining original code, twice."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import subprocess
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R/'tools'))
from apply_upstream_port import patch
with TemporaryDirectory() as d:
  root=Path(d);(root/'libspeex').mkdir();(root/'include/speex').mkdir(parents=True)
  (root/'libspeex/lsp.c').write_text('''#ifdef FIXED_POINT

void lsp_to_lpc(const spx_lsp_t *freq,spx_coef_t *ak,int lpcrdr, char *stack)
{
   int original = 1;
}

#else

void lsp_to_lpc(const spx_lsp_t *freq,spx_coef_t *ak,int lpcrdr, char *stack)
{
   int floating = 1;
}
#endif
''')
  (root/'libspeex/arch.h').write_text('#include "fixed_generic.h"\n')
  (root/'include/speex/speex_types.h').write_text('''#ifndef _TYPES_H
#define _TYPES_H
#if defined(__MACOS__)
typedef int spx_int32_t;
#else

#include "speex_config_types.h"

#endif
#endif
''')
  patch(root);a=(root/'libspeex/lsp.c').read_text()
  patch(root);b=(root/'libspeex/lsp.c').read_text()
  assert a==b
  assert a.count('int original = 1;')==1 and a.count('int floating = 1;')==1
  assert a.count('SPEEX_AVR_COMPACT_LSP_BEGIN')==1
  assert (root/'libspeex/avr_fastmul.h').exists()
  assert (root/'include/speex/speex_types.h').read_text().count('typedef int32_t  spx_int32_t;')==1
print('PASS: patcher idempotent, reference implementation and AVR types preserved')
