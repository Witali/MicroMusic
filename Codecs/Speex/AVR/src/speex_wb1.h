#ifndef SPEEX_WB1_H
#define SPEEX_WB1_H
#include <stddef.h>
#include <stdint.h>
/* Compact wideband: NB mode 3 + HB mode 1, 196 bits/20 ms (9.8 kbit/s).
 * Raw packets only; extract them from Ogg before calling this API.
 * The final normalized Q7 16-tap QMF approximates Xiph's 64-tap synthesis.
 * This profile does not produce bit-identical full-QMF Xiph PCM.
 *
 * Singleton, shares NB state: init before each independent stream; do not
 * interleave with the NB API. Output is synchronous: four callbacks of 80
 * signed16 samples/frame, valid only during each callback. Do not reenter.
 * -1 rejects parameters/packet mode without changing state; -2 indicates
 * unusable synthesis parameters (reset before continuing). No PLC/enhancer.
 * Build with SPEEX_ENABLE_WB1=1. Architecture/ASM selection uses the same
 * SPEEX_NB3_ARCH + SPEEX_NB3_ENABLE_ASM settings as the low-band decoder. */
#define SPEEX_WB1_PACKET_BYTES 25
#define SPEEX_WB1_SAMPLE_RATE 16000
#define SPEEX_WB1_FRAME_SAMPLES 320
typedef void (*speex_wb1_output_fn)(const int16_t *samples,uint8_t count,void *context);
void speex_wb1_init(void);
int speex_wb1_decode(const uint8_t *packet,size_t bytes,speex_wb1_output_fn output,void *context);
size_t speex_wb1_state_bytes(void);
#endif
