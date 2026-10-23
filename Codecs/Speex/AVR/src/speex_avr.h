#ifndef MICROMUSIC_SPEEX_AVR_H
#define MICROMUSIC_SPEEX_AVR_H
#include <stddef.h>
#include <stdint.h>

/* One static, non-reentrant decoder. No heap. Caller supplies 160 s16 samples.
 * Accepts exactly one 20-byte NB mode-3 packet. No Ogg, WB, DTX, PLC or stereo.
 * Reset before starting a new stream. Invalid packets leave state unchanged. */
#define SPEEX_AVR_PACKET_BYTES 20
#define SPEEX_AVR_FRAME_SAMPLES 160
void speex_avr_init(void);
int speex_avr_decode(const uint8_t *packet, size_t bytes, int16_t *pcm);
size_t speex_avr_state_bytes(void);
/* Host instrumentation; AVR returns zero because PUSH tracking is disabled. */
size_t speex_avr_scratch_peak(void);

#endif
