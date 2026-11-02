/* Exact forty-sample NB1 excitation primitive; private, portable interface. */
#ifndef MICROMUSIC_SPEEX_NB1_VOCODER_H
#define MICROMUSIC_SPEEX_NB1_VOCODER_H
#include "speex_platform.h"
#include "nb1_cache_layout.h"
#include <stddef.h>
#if SPEEX_ENABLE_NB1 && SPEEX_ENABLE_WB1
typedef struct {
    int16_t prior_pulse,prior_noise,mean;
    uint8_t phase,last;
} SpeexNb1Cursor;
_Static_assert(sizeof(SpeexNb1Cursor)==SPEEX_NB1_CURSOR_BYTES,"NB1 cursor size");
_Static_assert(offsetof(SpeexNb1Cursor,prior_pulse)==SPEEX_NB1_CURSOR_PULSE,"NB1 pulse offset");
_Static_assert(offsetof(SpeexNb1Cursor,prior_noise)==SPEEX_NB1_CURSOR_NOISE,"NB1 noise offset");
_Static_assert(offsetof(SpeexNb1Cursor,mean)==SPEEX_NB1_CURSOR_MEAN,"NB1 mean offset");
_Static_assert(offsetof(SpeexNb1Cursor,phase)==SPEEX_NB1_CURSOR_PHASE,"NB1 phase offset");
_Static_assert(offsetof(SpeexNb1Cursor,last)==SPEEX_NB1_CURSOR_LAST,"NB1 last offset");
void speex_nb1_synthesize40_c(int16_t *,const uint8_t *,const int16_t *,SpeexNb1Cursor *);
/* The zero primitive requires all previous[] and both new pulses to be zero.
 * It still consumes the cursor's old pulse/noise on the first sample. */
void speex_nb1_synthesize40_zero_c(int16_t *,const uint8_t *,const int16_t *,SpeexNb1Cursor *);
/* For contexts produced by NB1 preparation only: if gain>0, previous[0]==0
 * implies raw noise[0]==0, hence scale<=4096. Then all previous[] and both
 * pulses are zero. Gain==0 makes them zero at every scale. No new RAM flag. */
static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_nb1_context_is_zero(const int16_t *context)
{return context[SPEEX_NB1_PREVIOUS]==0;}
#if SPEEX_NB3_USE_AVR_ASM
void speex_nb1_synthesize40_avr(int16_t *,const uint8_t *,const int16_t *,SpeexNb1Cursor *);
void speex_nb1_synthesize40_zero_avr(int16_t *,const uint8_t *,const int16_t *,SpeexNb1Cursor *);
#define speex_nb1_synthesize40 speex_nb1_synthesize40_avr
#define speex_nb1_synthesize40_zero speex_nb1_synthesize40_zero_avr
#else
#define speex_nb1_synthesize40 speex_nb1_synthesize40_c
#define speex_nb1_synthesize40_zero speex_nb1_synthesize40_zero_c
#endif
#endif
#endif
