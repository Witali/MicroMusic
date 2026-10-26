#!/usr/bin/env python3
"""Apply explicit angle/LPC boundary substitutions to the frozen decoder source."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def generate():
    body=(ROOT/'src/spectral_decoder.c').read_text(encoding='utf-8')
    replacements={
        'state->previous_lsp[i] = i * PI / 11;':'state->previous_lsp[i] = codec2_lpc_initial_angle(i);',
        'current_lsp[i] = (PI / 4000.0) * (25.0f * params.lsp_25hz[i]);':'current_lsp[i] = codec2_lpc_grid_angle(params.lsp_25hz[i]);',
        'lsp_to_lpc(half ? current_lsp : state->previous_lsp, ak, 10);':'codec2_canonical_lsp_to_lpc(half ? current_lsp : state->previous_lsp, ak, 10);'}
    for old,new in replacements.items():assert body.count(old)==1,old;body=body.replace(old,new)
    prelude='/* Generated explicit canonical LPC boundaries; vendor and frozen sources remain intact. */\n#include "fixed_analysis.h"\n#include "lpc_math.h"\n#define compact_forward_lpc codec2_analysis_forward\n'
    return (prelude+body).encode('utf-8')
if __name__=='__main__':(ROOT/'src/canonical_decoder.c').write_bytes(generate())
