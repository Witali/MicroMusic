// Private multiplication backend, selected only by Lpx4Math.h.
#pragma once

// Portable C remains selectable on supported AVR targets as well as hosts.

static inline __attribute__((always_inline)) int32_t lpx4Mul8x16(int8_t x,int16_t y){
    return (int32_t)x*y;
}

static inline __attribute__((always_inline)) int32_t lpx4Mul8xU16(int8_t x,uint16_t y){
    return (int32_t)x*y;
}

static LPX4_MUL_INLINE int32_t lpx4Mul16(int16_t x,int16_t y){
    return (int32_t)x*y;
}
