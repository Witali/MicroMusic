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
    mul = lib / 'avr_fastmul.h'
    mul.write_text(replace(mul.read_text(), 'static inline spx_word32_t',
                           'static inline __attribute__((always_inline)) spx_word32_t'))
    path = lib / 'nb_celp.c'
    text = path.read_text()
    text = replace(text, '#define SUBMODE(x) st->submodes[st->submodeID]->x',
                   '#include "profile_mode.h"\n#include "innovation.h"\n#define SUBMODE(x) speex_avr_submode.x')
    # Keep the original nb_decode body, dropping generic initialization/ctl/PLC.
    start = text.index('void *nb_decoder_init(')
    stop = text.index('int nb_decode(', start)
    text = text[:start] + text[stop:]
    text = replace(text, 'int nb_decode(', '__attribute__((noinline)) int nb_decode(')
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
    text = replace(text,
        'SUBMODE(innovation_unquant)(innov, SUBMODE(innovation_params), NB_SUBFRAME_SIZE, bits, stack, &st->seed);',
        'speex_avr_innovation(exc, exc32, bits, ener);')
    decode_start = text.index('int nb_decode(')
    text = text[:decode_start] + replace(text[decode_start:], 'signal_mul(innov, innov, ener, NB_SUBFRAME_SIZE);', '')
    # The fixed NB3 path writes every final excitation sample directly.
    # Unsupported vocoder/double-codebook/innovation-save paths are dead.
    before, body = text[:decode_start], text[decode_start:]
    body = replace(body, '   ALLOC(innov, NB_SUBFRAME_SIZE, spx_sig_t);', '')
    body = replace(body, '         SPEEX_MEMSET(innov, 0, NB_SUBFRAME_SIZE);', '')
    body = replace(body, '''            for (i=0;i<NB_SUBFRAME_SIZE;i++)
               exc[i]=EXTRACT16(SATURATE32(PSHR32(ADD32(SHL32(exc32[i],1),innov[i]),SIG_SHIFT),32767));''', '')
    text = before + body
    text = replace(text,
        '         st->interp_qlpc[i] = ak[i];',
        '''         st->interp_qlpc[i] = ak[i];
#ifdef SPEEX_AVR_OUTPUT_HOOK
      {
         extern void speex_avr_output(const spx_word16_t *, uint8_t);
         speex_avr_output(sp, NB_SUBFRAME_SIZE);
      }
#endif''')
    path.write_text(text)

    path = lib / 'ltp.c'
    text = path.read_text()
    first = '''      for (j=0;j<tmp1;j++)
         exc_out[j]=MAC16_16(exc_out[j],gain[2-i],exc[j-pp]);'''
    second = '''      for (j=tmp1;j<tmp3;j++)
         exc_out[j]=MAC16_16(exc_out[j],gain[2-i],exc[j-pp-pitch]);'''
    text = replace(text, first, '''#ifdef __AVR__
      extern void speex_avr_pitch_add(spx_word32_t *, const spx_word16_t *, spx_word16_t, uint8_t);
      speex_avr_pitch_add(exc_out, exc-pp, gain[2-i], tmp1);
#else
''' + first + '\n#endif')
    text = replace(text, second, '''#ifdef __AVR__
      speex_avr_pitch_add(exc_out+tmp1, exc+tmp1-pp-pitch, gain[2-i], tmp3-tmp1);
#else
''' + second + '\n#endif')
    path.write_text(text)

    for filename, functions in [('filters.c', ['iir_mem16', 'signal_mul']),
                                ('ltp.c', ['pitch_unquant_3tap']),
                                ('quant_lsp.c', ['lsp_unquant_lbr'])]:
        path = lib / filename
        text = path.read_text()
        for function in functions:
            text = text.replace('void ' + function + '(',
                                '__attribute__((noinline)) void ' + function + '(')
        path.write_text(text)
    path = lib / 'nb_celp.h'
    text = path.read_text()
    text = replace(text, '   SpeexCallback speex_callbacks[SPEEX_MAX_CALLBACKS];', '')
    text = replace(text, '   SpeexCallback user_callback;', '')
    # With no PLC/enhancer, pitch_unquant_3tap reads at most pitch+1 samples
    # backwards (pitch <= 144). Synthesis needs only the preceding 40 samples.
    text = replace(text, '(NB_FRAME_SIZE+NB_SUBFRAME_SIZE+6)', '(NB_PITCH_END+2)')
    path.write_text(text)

    path = lib / 'lsp.c'
    text = path.read_text()
    start = text.index('void lsp_to_lpc(', text.index('/* SPEEX_AVR_COMPACT_LSP_BEGIN */'))
    stop = text.index('\n#else', start)
    fragment = Path(__file__).resolve().parents[1] / 'src/compact_lsp.c.inc'
    text = text[:start] + fragment.read_text() + text[stop:]
    text = text.replace('void lsp_to_lpc(', '__attribute__((noinline)) void lsp_to_lpc(')
    path.write_text(text)

    path = lib / 'filters.c'
    text = path.read_text()
    start = text.index('void iir_mem16(')
    stop = text.index('\n#endif', start)
    function = text[start:stop]
    begin = function.index('      for (j=0;j<ord-1;j++)')
    end = function.index('      y[i] = yi;', begin)
    original = function[begin:end]
    function = function[:begin] + '''#ifdef __AVR__
      extern void speex_nb8_lpc_update_asm(spx_mem_t *, const spx_coef_t *, spx_word16_t);
      speex_nb8_lpc_update_asm(mem, den, nyi);
#else
''' + original + '#endif\n' + function[end:]
    text = text[:start] + function + text[stop:]
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
