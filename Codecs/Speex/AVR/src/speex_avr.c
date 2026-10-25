#include "speex_avr.h"
#include "speex_platform.h"
#include "nb_celp.h"
#include <string.h>
#if SPEEX_NB3_CHECK_SCRATCH
#include <stdlib.h>
#endif

static DecState decoder;
/* Excitation uses qlsp (20 B) and four indices. Synthesis reuses offset 20
 * for ak, then appends interp at 40. Peak = 60 B; host checks each PUSH. */
_Alignas(4) static uint32_t scratch[15];
static size_t scratch_peak;

#if SPEEX_NB3_CHECK_SCRATCH
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
    decoder.stack = (char *)scratch;
    scratch_peak = 0;
}

int speex_avr_decode(const uint8_t *packet, size_t bytes, int16_t *pcm)
{
    if (!packet || !pcm || bytes != 20 || (packet[0] >> 3) != 3) return -1;
    return nb_decode(&decoder, packet, pcm);
}

size_t speex_avr_state_bytes(void) { return sizeof(decoder) + sizeof(scratch); }
size_t speex_avr_scratch_peak(void) { return scratch_peak; }

#if SPEEX_ENABLE_WB1
int speex_wb_decode_low(const uint8_t *packet)
{
    return nb_decode(&decoder,packet,0);
}
#endif
