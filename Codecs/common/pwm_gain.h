/* Constant output gain, independent of codec state, hardware and ISR code.
 * Silence 128 is exact. Q7 rounding is nearest, with ties toward +infinity.
 * The release builder proves that its complete input does not saturate.
 * Other inputs saturate rather than wrap. Default unity emits no code. */
#ifndef MICROMUSIC_PWM_GAIN_H
#define MICROMUSIC_PWM_GAIN_H
#include <stdint.h>
#ifndef PWM_GAIN_Q7
#define PWM_GAIN_Q7 128
#endif
#if PWM_GAIN_Q7 < 128 || PWM_GAIN_Q7 > 255
#error PWM_GAIN_Q7 must be between 128 and 255
#endif
static inline uint8_t micromusic_pwm_gain(uint8_t value)
{
#if PWM_GAIN_Q7 == 128
    return value;
#else
    /* 255*255+64 fits uint16_t. Use unsigned arithmetic to avoid shifting
     * negative values. The compiler removes every unused constant term.
     * No software multiply helper is needed on cores without MUL. */
    uint16_t product = 64;
#if PWM_GAIN_Q7 & 1
    product += value;
#endif
#if PWM_GAIN_Q7 & 2
    product += (uint16_t)value << 1;
#endif
#if PWM_GAIN_Q7 & 4
    product += (uint16_t)value << 2;
#endif
#if PWM_GAIN_Q7 & 8
    product += (uint16_t)value << 3;
#endif
#if PWM_GAIN_Q7 & 16
    product += (uint16_t)value << 4;
#endif
#if PWM_GAIN_Q7 & 32
    product += (uint16_t)value << 5;
#endif
#if PWM_GAIN_Q7 & 64
    product += (uint16_t)value << 6;
#endif
    product += (uint16_t)value << 7;
    const int16_t result = (int16_t)(product >> 7) + 128 - PWM_GAIN_Q7;
    return result < 0 ? 0 : result > 255 ? 255 : (uint8_t)result;
#endif
}
#endif
