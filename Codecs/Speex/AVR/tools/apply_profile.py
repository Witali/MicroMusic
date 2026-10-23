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
    path = lib / 'nb_celp.c'
    text = path.read_text()
    text = replace(text, '#define SUBMODE(x) st->submodes[st->submodeID]->x',
                   '#include "profile_mode.h"\n#define SUBMODE(x) speex_avr_submode.x')
    # Keep the original nb_decode body, dropping generic initialization/ctl/PLC.
    start = text.index('void *nb_decoder_init(')
    stop = text.index('int nb_decode(', start)
    text = text[:start] + text[stop:]
    start = text.index('   /* Check if we\'re in DTX mode*/')
    stop = text.index('   /* Shift all buffers by one frame */', start)
    text = text[:start] + '   if (!bits) return -2;\n\n' + text[stop:]
    # Wrapper fixes these settings; make them compile-time constants so dead
    # code (enhancer, rescaling, highpass, lost-frame handling) is discarded.
    text = text.replace('if (st->count_lost)', 'if (0)')
    text = text.replace('if (st->submodes[st->submodeID] == NULL)', 'if (0)')
    text = text.replace('st->lpc_enh_enabled &&', '0 &&')
    text = text.replace('if (st->highpass_enabled)', 'if (0)')
    text = text.replace('if (st->innov_save)', 'if (0)')
    text = text.replace('st->count_lost, offset, st->last_pitch_gain, 0', '0, offset, 0, 0')
    path.write_text(text)
    path = lib / 'nb_celp.h'
    text = path.read_text()
    text = replace(text, '   SpeexCallback speex_callbacks[SPEEX_MAX_CALLBACKS];', '')
    text = replace(text, '   SpeexCallback user_callback;', '')
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
#undef ALIGN
#define ALIGN(stack, size) ((stack) += ((size) - (uintptr_t)(stack)) & ((size) - 1))
#ifndef __AVR__
#include <stddef.h>
void *speex_avr_push(char **position, size_t bytes, size_t alignment);
#undef PUSH
#define PUSH(stack, size, type) ((type *)speex_avr_push(&(stack), (size)*sizeof(type), sizeof(type)))
#endif
''' + text[at:]
    path.write_text(text)
