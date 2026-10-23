"""Specialize a disposable Xiph tree for the documented lossless NB3 profile.

The original synthesis, LSP interpolation, gain, pitch and innovation arithmetic
is retained. The general API and unsupported packet paths are excluded. Apply
only after the guarded handoff compact-LSP / tight-excitation patches.
"""
from pathlib import Path
import re


def replace(text, old, new, count=1):
    if text.count(old) != count:
        raise RuntimeError(f'Unexpected upstream source for {old[:80]!r}')
    return text.replace(old, new)


def apply(source: Path):
    lib = source / 'libspeex'
    # The two-MUL pitch kernel uses the restricted NB3 codebook's signed8
    # unscaled gains. Check that contract before installing any specialization.
    pitch_table = re.search(r'gain_cdbk_lbr\[128\]\s*=\s*\{([^}]+)\}',
                           (lib / 'gain_table_lbr.c').read_text())[1]
    pitch_values = [int(v) for v in pitch_table.split(',') if v.strip()]
    if len(pitch_values) != 128 or any(not -128 <= v+32 <= 127
        for i, v in enumerate(pitch_values) if i % 4 != 3):
        raise RuntimeError('NB3 pitch gains do not satisfy the signed8 ASM contract')
    if max(sum(abs(pitch_values[i+j]+32) for j in range(3))
           for i in range(0,128,4))*32768 >= (1<<23):
        raise RuntimeError('NB3 pitch sums exceed packed signed24')
    mul = lib / 'avr_fastmul.h'
    mul.write_text((Path(__file__).resolve().parents[1] / 'src/avr_multiply.h').read_text())
    path = lib / 'arch.h'
    # Fixed-point C optimizations also apply outside AVR and do not require
    # the optional hardware-multiply flag. Keep the override after fastmul.
    path.write_text(replace(path.read_text(),
                           '#include "avr_fastmul.h"\n#endif',
                           '#include "avr_fastmul.h"\n#endif\n#include "avr_fixed.h"'))
    path.write_text(replace(path.read_text(), '#include "fixed_generic.h"',
                           '#include "fixed_generic.h"\n#include "speex_platform.h"'))
    path = lib / 'nb_celp.c'
    text = path.read_text()
    text = replace(text, '#define SUBMODE(x) st->submodes[st->submodeID]->x',
                   '#include "profile_mode.h"\n#include "innovation.h"\n#define SUBMODE(x) speex_avr_submode.x')
    # Retain the original license, includes and constants; the restricted body
    # omits only state/control work outside the public NB3 profile.
    start = text.index('void *nb_decoder_init(')
    fragment = Path(__file__).resolve().parents[1] / 'src/nb_decode.c.inc'
    gains = [int(v) for v in re.search(r'ol_gain_table\[32\]=\{([^}]+)\}',text)[1].split(',')]
    corrections = [int(v) for v in re.search(r'exc_gain_quant_scal1\[2\]=\{([^}]+)\}',text)[1].split(',')]
    # Exact two-stage Q15/Q14 floors, generated from pinned upstream constants.
    values = [(c*((28406*g)//32768))//16384 for g in gains for c in corrections]
    assert len(values)==64 and min(values)>0 and max(values)==120988612
    table = '\nstatic const spx_word32_t nb3_gain_table[64] AVR_TABLE={' + ','.join(map(str,values)) + '};\n'
    text = text[:start] + table + fragment.read_text() + '\n#endif /* DISABLE_DECODER */\n'
    path.write_text(text)

    for filename, functions in [('filters.c', ['iir_mem16', 'signal_mul']),
                                ('ltp.c', ['pitch_unquant_3tap']),
                                ('quant_lsp.c', ['lsp_unquant_lbr'])]:
        path = lib / filename
        text = path.read_text()
        for function in functions:
            text = text.replace('void ' + function + '(',
                                'SPEEX_NB3_NOINLINE void ' + function + '(')
        path.write_text(text)
    path = lib / 'nb_celp.h'
    text = path.read_text()
    start = text.index('typedef struct DecState {')
    stop = text.index('} DecState;',start)+len('} DecState;')
    text = text[:start] + '#include "profile_state.h"' + text[stop:]
    # Maximum backward pitch read is pitch+1 (<=145); synthesis needs 40.
    # No PLC/enhancer/vector lookahead: exactly 145 history + 160 current.
    text = replace(text, '(NB_FRAME_SIZE+NB_SUBFRAME_SIZE+6)', '(NB_PITCH_END+1)')
    text = replace(text, '#define NB_DEC_SHIFT_COUNT (NB_DEC_EXC_OFFSET+6)',
                         '#define NB_DEC_SHIFT_COUNT NB_DEC_EXC_OFFSET')
    path.write_text(text)

    path = lib / 'lsp.c'
    text = path.read_text()
    start = text.index('void lsp_to_lpc(', text.index('/* SPEEX_AVR_COMPACT_LSP_BEGIN */'))
    stop = text.index('\n#else', start)
    fragment = Path(__file__).resolve().parents[1] / 'src/compact_lsp.c.inc'
    text = text[:start] + fragment.read_text() + text[stop:]
    text = text.replace('void lsp_to_lpc(', 'SPEEX_NB3_NOINLINE void lsp_to_lpc(')
    path.write_text(text)

    path = lib / 'filters.c'
    text = path.read_text()
    start = text.index('SPEEX_NB3_NOINLINE void iir_mem16(')
    stop = text.index('\n#endif', start)
    fragment = Path(__file__).resolve().parents[1] / 'src/iir_direct.c.inc'
    text = text[:start] + fragment.read_text() + text[stop:]
    path.write_text(text)

    # Tables are marked at their definitions. Every decoder access uses an
    # explicit width/sign read, while parameter structs retain ordinary pointers.
    for name in ['lsp_tables_nb.c', 'gain_table_lbr.c', 'exc_10_32_table.c']:
        path = lib / name
        text = path.read_text()
        text, n = re.subn(r'(const signed char \w+\[\d+\])\s*=', r'\1 AVR_TABLE =', text)
        if not n:
            raise RuntimeError('Codebook declaration not found in ' + name)
        path.write_text('#include "avr_tables.h"\n' + text)
    for name, pattern in [
        ('quant_lsp.c', r'(cdbk_nb(?:_low[12]|_high[12])?)\[([^\]]+)\]'),
        ('ltp.c', r'(gain_cdbk)\[([^\]]+)\]'),
        ('cb_search.c', r'(shape_cb)\[((?:[^\[\]]|\[[^\]]+\])+)\]')]:
        path = lib / name
        text = path.read_text()
        # Do not rewrite extern declarations; accesses have non-empty indices.
        text, n = re.subn(pattern, r'AVR_READ_I8(&\1[\2])', text)
        if not n:
            raise RuntimeError('Codebook reads not found in ' + name)
        path.write_text('#include "avr_tables.h"\n' + text)
    path = lib / 'nb_celp.c'
    text = path.read_text()
    for table, bits in [('ol_gain_table', 32), ('exc_gain_quant_scal1', 16),
                        ('exc_gain_quant_scal3', 16)]:
        text = re.sub(r'(' + table + r'\[\d+\])=', r'\1 AVR_TABLE =', text)
        text = re.sub(r'\b' + table + r'\[(qe|q_energy)\]',
                      rf'AVR_READ_I{bits}(&{table}[\1])', text)
    path.write_text('#include "avr_tables.h"\n' + text)

    # Use a bounds-checked scratch allocator on the host. AVR keeps the original
    # pointer allocator; its peak and C stack are checked by the ISA simulation.
    path = lib / 'stack_alloc.h'
    text = path.read_text()
    at = text.rfind('#endif')
    text = text[:at] + '''
#include <stdint.h>
#include "speex_platform.h"
#undef ALIGN
#define ALIGN(stack, size) ((stack) += ((size) - (uintptr_t)(stack)) & ((size) - 1))
#if SPEEX_NB3_CHECK_SCRATCH
#include <stddef.h>
void *speex_avr_push(char **position, size_t bytes, size_t alignment);
#undef PUSH
#define PUSH(stack, size, type) ((type *)speex_avr_push(&(stack), (size)*sizeof(type), sizeof(type)))
#endif
''' + text[at:]
    path.write_text(text)
