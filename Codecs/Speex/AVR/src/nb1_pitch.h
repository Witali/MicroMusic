/* Exact finite pitch-root map for Xiph Speex 1.2.1 NB1 excitation.
 * Derived from math_approx.h spx_sqrt(2*pitch), pitch=17..144.
 * Xiph BSD provenance and license: vendor/speex-1.2.1/COPYING. */
#ifndef MICROMUSIC_SPEEX_NB1_PITCH_H
#define MICROMUSIC_SPEEX_NB1_PITCH_H
#include "avr_tables.h"
#include "math_approx.h"

/* This switch is independent of arithmetic backend and table-memory access.
 * Set zero to use the original portable arithmetic, including on AVR. */
#ifndef SPEEX_NB1_PITCH_ROOT_TABLE
#define SPEEX_NB1_PITCH_ROOT_TABLE 1
#endif
#if SPEEX_NB1_PITCH_ROOT_TABLE != 0 && SPEEX_NB1_PITCH_ROOT_TABLE != 1
#error SPEEX_NB1_PITCH_ROOT_TABLE must be zero or one
#endif

/* Complete seven-bit packet domain, with the original +17 pitch offset.
 * Values are exact outputs of the fixed-point polynomial, not real sqrt(). */
static const uint8_t speex_nb1_pitch_root_table[128] AVR_TABLE={
    5,6,6,6,6,6,6,6,7,7,7,7,7,7,7,8,
    8,8,8,8,8,8,8,8,9,9,9,9,9,9,9,9,
    9,9,10,10,10,10,10,10,10,10,10,10,11,11,11,11,
    11,11,11,11,11,11,11,12,12,12,12,12,12,12,12,12,
    12,12,12,12,13,13,13,13,13,13,13,13,13,13,13,13,
    13,13,14,14,14,14,14,14,14,14,14,14,14,14,14,14,
    15,15,15,15,15,15,15,15,15,15,15,15,15,15,15,16,
    16,16,16,16,16,16,16,16,16,16,16,16,16,16,16,16};
static SPEEX_NB3_ALWAYS_INLINE uint8_t speex_nb1_pitch_root_table_c(uint8_t pitch)
{return (uint8_t)AVR_READ_I8(speex_nb1_pitch_root_table+(uint8_t)(pitch-17));}
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb1_pitch_root_c(uint8_t pitch)
{return spx_sqrt(2*(int16_t)pitch);}
static SPEEX_NB3_ALWAYS_INLINE int16_t speex_nb1_pitch_root(uint8_t pitch)
{
#if SPEEX_NB1_PITCH_ROOT_TABLE
    return speex_nb1_pitch_root_table_c(pitch);
#else
    return speex_nb1_pitch_root_c(pitch);
#endif
}
#endif
