#pragma once
#include <stdint.h>

// Apply only to the final postfilter output, never to LPC/excitation history.
// Q14 * unsigned Q4.12 fits signed32, including a full-scale negative sample.
static inline int16_t lpx4FileGainQ14Reference(int16_t sample,uint16_t gain) {
    const int32_t value=((int32_t)sample*(int32_t)gain+2048)>>12;
    return value<-16384?-16384:value>16384?16384:(int16_t)value;
}
static inline int16_t lpx4FileGainQ14Unsigned(int16_t sample,uint16_t gain) {
    const uint16_t magnitude=sample<0?(uint16_t)(-(int32_t)sample):(uint16_t)sample;
    const uint32_t product=(uint32_t)magnitude*(uint32_t)gain;
    const int32_t signedProduct=sample<0?-(int32_t)product:(int32_t)product;
    const int32_t value=(signedProduct+2048)>>12;
    return value<-16384?-16384:value>16384?16384:(int16_t)value;
}
#ifndef LPX4_FILE_GAIN_UNSIGNED_MULTIPLY
#if defined(__AVR__) && !defined(__AVR_HAVE_MUL__)
#define LPX4_FILE_GAIN_UNSIGNED_MULTIPLY 1
#else
#define LPX4_FILE_GAIN_UNSIGNED_MULTIPLY 0
#endif
#endif
#if LPX4_FILE_GAIN_UNSIGNED_MULTIPLY != 0 && LPX4_FILE_GAIN_UNSIGNED_MULTIPLY != 1
#error LPX4_FILE_GAIN_UNSIGNED_MULTIPLY must be 0 or 1
#endif
static inline int16_t lpx4FileGainQ14(int16_t sample,uint16_t gain) {
#if LPX4_FILE_GAIN_UNSIGNED_MULTIPLY
    return lpx4FileGainQ14Unsigned(sample,gain);
#else
    return lpx4FileGainQ14Reference(sample,gain);
#endif
}
static inline int16_t lpx4FileGainPcm16(int16_t sample,uint16_t gain) {
    const int16_t q14=sample==32767?16384:sample/2;
    const int32_t value=(int32_t)lpx4FileGainQ14(q14,gain)*2;
    return value>32767?32767:(int16_t)value;
}
