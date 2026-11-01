#pragma once
#ifndef LPX25_ENABLE_ASM
#define LPX25_ENABLE_ASM 0
#endif
#if LPX25_ENABLE_ASM != 0 && LPX25_ENABLE_ASM != 1
#error LPX25_ENABLE_ASM must be 0 or 1
#endif
#if LPX25_ENABLE_ASM && defined(__AVR__) && defined(__AVR_ARCH__) && __AVR_ARCH__ == 25 && \
    !defined(__AVR_HAVE_MUL__) && defined(__GNUC__) && !defined(__clang__)
#define LPX25_USE_ASM 1
#else
#define LPX25_USE_ASM 0
#endif
#ifndef __ASSEMBLER__
#include <stdint.h>
extern "C" {
int32_t proto_mul(int16_t x,int16_t y) __attribute__((noinline));
int32_t proto_shift12(int32_t value) __attribute__((noinline));
int32_t proto_shift14(int32_t value) __attribute__((noinline));
}
#endif
