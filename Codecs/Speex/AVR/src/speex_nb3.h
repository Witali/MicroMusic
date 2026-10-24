/* Architecture-neutral source API. Legacy exported symbol names are retained
 * for compatibility; neither this header nor the C backend needs AVR headers. */
#ifndef MICROMUSIC_SPEEX_NB3_H
#define MICROMUSIC_SPEEX_NB3_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

/* One static, non-reentrant decoder; no heap or hardware output.
 * Call init before a stream. Supply 160 native-endian signed16 PCM samples.
 * Input is one 20-byte NB mode-3 packet, in packet byte order on every CPU.
 * Invalid arguments return -1 without changing state or output.
 * Ogg, WB, DTX, PLC, stereo and simultaneous decoder instances are unsupported. */
#define SPEEX_NB3_PACKET_BYTES 20
#define SPEEX_NB3_FRAME_SAMPLES 160
#define SPEEX_NB3_SAMPLE_RATE 8000
void speex_avr_init(void);
int speex_avr_decode(const uint8_t *packet, size_t bytes, int16_t *pcm);
size_t speex_avr_state_bytes(void);
/* Returns zero when SPEEX_NB3_CHECK_SCRATCH=0. */
size_t speex_avr_scratch_peak(void);

#define speex_nb3_init speex_avr_init
#define speex_nb3_decode speex_avr_decode
#define speex_nb3_state_bytes speex_avr_state_bytes
#define speex_nb3_scratch_peak speex_avr_scratch_peak
#ifdef __cplusplus
}
#endif
#endif
