/* Neutral names for the NB3/NB4 singleton API. Legacy names stay exported. */
#ifndef MICROMUSIC_SPEEX_NB_H
#define MICROMUSIC_SPEEX_NB_H
#include "speex_nb3.h"
#define SPEEX_NB_FRAME_SAMPLES SPEEX_NB3_FRAME_SAMPLES
#define SPEEX_NB_SAMPLE_RATE SPEEX_NB3_SAMPLE_RATE
#define speex_nb_init speex_avr_init
#define speex_nb_decode speex_avr_decode
#define speex_nb_state_bytes speex_avr_state_bytes
#define speex_nb_scratch_peak speex_avr_scratch_peak
#endif
