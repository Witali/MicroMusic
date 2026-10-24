#!/usr/bin/env python3
"""Experimental, OFF-BY-DEFAULT Speex NB excBuf shortening.

Valid only for NB decoder pitch <=144 with at least 160 samples of history.
Requires complete upstream ASan+PCM tests before use on target hardware.
"""
from pathlib import Path
import argparse

HEADER_REPLACE = '''#if defined(SPEEX_AVR_TIGHT_EXC)
/* NB 10-pole, 160 samples/frame; keep >=160 prior excitation samples.
 * Buffer is H history + 160 current + 6 pad = 372 x int16_t.
 * Requires this restricted decoder-only profile; not general wideband.
 */
#define NB_DEC_EXC_OFFSET (NB_FRAME_SIZE+NB_SUBFRAME_SIZE+6)
#define NB_DEC_SHIFT_COUNT (NB_DEC_EXC_OFFSET+6)
#define NB_DEC_BUFFER (NB_FRAME_SIZE+NB_DEC_SHIFT_COUNT)
#else
#define NB_DEC_EXC_OFFSET (2*NB_PITCH_END+NB_SUBFRAME_SIZE+6)
#define NB_DEC_SHIFT_COUNT (2*NB_PITCH_END+NB_SUBFRAME_SIZE+12)
#define NB_DEC_BUFFER (NB_FRAME_SIZE+NB_DEC_SHIFT_COUNT)
#endif'''

def apply(root: Path):
    h=root/'libspeex/nb_celp.h';c=root/'libspeex/nb_celp.c'
    ht=h.read_text();ct=c.read_text()
    if '#define NB_DEC_EXC_OFFSET' in ht:
        print('Excitation guard already installed');return
    orig='#define NB_DEC_BUFFER (NB_FRAME_SIZE+2*NB_PITCH_END+NB_SUBFRAME_SIZE+12)'
    if ht.count(orig)!=1:raise RuntimeError('Unexpected header; no files touched')
    offset='2*NB_PITCH_END + NB_SUBFRAME_SIZE + 6'
    shift='2*NB_PITCH_END + NB_SUBFRAME_SIZE + 12'
    if ct.count(offset)!=2 or ct.count(shift)!=2:raise RuntimeError('Unexpected nb_celp.c; no files touched')
    ht=ht.replace(orig,HEADER_REPLACE)
    ct=ct.replace(offset,'NB_DEC_EXC_OFFSET').replace(shift,'NB_DEC_SHIFT_COUNT')
    h.write_text(ht);c.write_text(ct)
    print('Installed experimental -DSPEEX_AVR_TIGHT_EXC guard: 500 -> 372 elements')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('speex_source_root',type=Path)
    apply(ap.parse_args().speex_source_root)
