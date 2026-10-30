#include "speex_avr.h"
#include "speex_platform.h"
#include "nb_celp.h"
#include "packet_mode.h"
#include <string.h>
#if SPEEX_NB3_CHECK_SCRATCH
#include <stdlib.h>
#endif

static DecState decoder;
/* Delta occupies 20 B. Excitation indices, interpolated angles and LPC
 * coefficients reuse offset 20 in that order. The converter consumes every
 * angle before writing coefficients. Peak = 40 B; host checks each PUSH. */
_Alignas(4) static uint32_t scratch[10];
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
#if SPEEX_ENABLE_NB1
    decoder.seed=1000;
#endif
    decoder.stack = (char *)scratch;
    scratch_peak = 0;
}

int speex_avr_decode(const uint8_t *packet, size_t bytes, int16_t *pcm)
{
#if SPEEX_ENABLE_LOW_RATES
    if(!packet || !pcm || !bytes)return -1;
    unsigned bits=speex_nb_packet_bits(packet[0]>>3);
    if(!bits || bytes!=(bits+7)/8)return -1;
#elif SPEEX_ENABLE_NB4
    if (!packet || !pcm) return -1;
    if((bytes!=20 || (packet[0]>>3)!=3) && (bytes!=28 || (packet[0]>>3)!=4)) return -1;
#else
    if (!packet || !pcm || bytes != 20 || (packet[0] >> 3) != 3) return -1;
#endif
    return nb_decode(&decoder, packet, pcm);
}

size_t speex_avr_state_bytes(void) { return sizeof(decoder) + sizeof(scratch); }
size_t speex_avr_scratch_peak(void) { return scratch_peak; }

#if SPEEX_ENABLE_WB1
#if SPEEX_ENABLE_NB1
uint32_t speex_wb_noise_seed(void){return decoder.seed;}
#endif
int speex_wb_decode_low(const uint8_t *packet)
{
    return nb_decode(&decoder,packet,0);
}
#endif
