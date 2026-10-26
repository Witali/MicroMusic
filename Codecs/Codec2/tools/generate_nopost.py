#!/usr/bin/env python3
"""Make an explicit experimental decoder with the optional LPC postfilter off."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def generate_decoder():
    body = (ROOT / 'src/canonical_decoder.c').read_text(encoding='utf-8')
    start = body.index('static void amplitudes(')
    end = body.index('\nstatic void background_filter(', start)
    old = body[start:end]
    tail = old[old.index('    float r = TWO_PI / 512;'):]
    replacement = '''/* Upstream aks_to_M2 with pf=0: scale the unmodified power by E.
 * The separate phase/background postfilter remains enabled. */
static void amplitudes(float ak[11], compact_model *model, float energy, compact_transform *buffer) {
    (void)ak;
    for (unsigned i = 0; i < 256; ++i) buffer->frequency[i].r *= energy;
'''
    body = body[:start] + replacement + tail + body[end:]
    for line in ('#include "fixed_fifth.h"\n', '#include "fixed_weight.h"\n'):
        assert body.count(line) == 1
        body = body.replace(line, '')
    return ('/* Generated experiment: optional LPC postfilter and its bass boost disabled. */\n' + body).encode('utf-8')


def generate_oracle():
    body = (ROOT / 'tests/upstream_decode.c').read_text(encoding='utf-8')
    old = 'c2->lpc_pf = c2->bass_boost = 1;'
    assert body.count(old) == 1
    body = body.replace(old, 'c2->lpc_pf = c2->bass_boost = 0;')
    return ('/* Generated original upstream oracle with its supported LPC postfilter disabled. */\n' + body).encode('utf-8')


if __name__ == '__main__':
    (ROOT / 'src/nopost_decoder.c').write_bytes(generate_decoder())
    (ROOT / 'tests/upstream_nopost.c').write_bytes(generate_oracle())
