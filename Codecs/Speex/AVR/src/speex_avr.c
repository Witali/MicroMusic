#include "speex_avr.h"
#include "nb_celp.h"
#include <string.h>
#ifndef __AVR__
#include <stdlib.h>
#endif

static DecState decoder;
/* qlsp + ak + innovation + pitch excitation + interpolated LSP = 380 B.
 * The innovation index/sign arrays overlap interpolated LSP in time.
 * 400 B retains alignment/headroom; host builds check every PUSH. */
static uint32_t scratch[100];
static size_t scratch_peak;

#ifndef __AVR__
void *speex_avr_push(char **position, size_t bytes, size_t alignment)
{
    uintptr_t p = (uintptr_t)*position;
    uintptr_t aligned = (p + alignment - 1) & ~(uintptr_t)(alignment - 1);
    uintptr_t end = aligned + bytes;
    size_t used = end - (uintptr_t)scratch;
    if (p < (uintptr_t)scratch || used > sizeof(scratch)) abort();
    if (used > scratch_peak) scratch_peak = used;
    *position = (char *)end;
    return (void *)aligned;
}
#endif

void speex_avr_init(void)
{
    memset(&decoder, 0, sizeof(decoder));
    memset(scratch, 0, sizeof(scratch));
    decoder.first = 1;
    decoder.submodeID = 3;
    decoder.stack = (char *)scratch;
    scratch_peak = 0;
}

int speex_avr_decode(const uint8_t *packet, size_t bytes, int16_t *pcm)
{
    SpeexBits bits;
    if (!packet || !pcm || bytes != 20 || (packet[0] >> 3) != 3) return -1;
    memset(&bits, 0, sizeof(bits));
    bits.chars = (char *)packet;
    bits.nbBits = 160;
    bits.buf_size = 20;
    bits.bitPtr = 5; /* already validated the wideband bit and 4-bit mode */
    return nb_decode(&decoder, &bits, pcm);
}

size_t speex_avr_state_bytes(void) { return sizeof(decoder) + sizeof(scratch); }
size_t speex_avr_scratch_peak(void) { return scratch_peak; }
