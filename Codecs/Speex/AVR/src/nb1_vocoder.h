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
#if SPEEX_NB3_USE_AVR_ASM
void speex_nb1_synthesize40_avr(int16_t *,const uint8_t *,const int16_t *,SpeexNb1Cursor *);
#define speex_nb1_synthesize40 speex_nb1_synthesize40_avr
#else
#define speex_nb1_synthesize40 speex_nb1_synthesize40_c
#endif
#endif
#endif
