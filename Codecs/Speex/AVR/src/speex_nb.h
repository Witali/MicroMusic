/* Neutral names for the enabled NB singleton modes. Legacy names stay exported.
 * Optional NB2/NB8/NB1: 5.95/3.95/2.15 kbit/s, 15/10/6 bytes per frame. */
#ifndef MICROMUSIC_SPEEX_NB_H
#define MICROMUSIC_SPEEX_NB_H
#include "speex_nb3.h"
#define SPEEX_NB_FRAME_SAMPLES SPEEX_NB3_FRAME_SAMPLES
#define SPEEX_NB_SAMPLE_RATE SPEEX_NB3_SAMPLE_RATE
#define SPEEX_NB2_PACKET_BYTES 15
#define SPEEX_NB8_PACKET_BYTES 10
#define SPEEX_NB1_PACKET_BYTES 6
#define SPEEX_NB_MAX_PACKET_BYTES 28
#define speex_nb_init speex_avr_init
#define speex_nb_decode speex_avr_decode
#define speex_nb_state_bytes speex_avr_state_bytes
#define speex_nb_scratch_peak speex_avr_scratch_peak
#endif
