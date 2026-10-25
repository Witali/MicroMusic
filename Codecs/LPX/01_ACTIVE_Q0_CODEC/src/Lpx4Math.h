#pragma once
#include <stdint.h>

// Optional platform header may select an architecture and arithmetic backend.
// Memory access remains controlled by the compiler's real __AVR__ macro.
#define LPX4_ARCH_GENERIC 0
#define LPX4_ARCH_AVR5 1
#ifdef LPX4_PLATFORM_HEADER
#include LPX4_PLATFORM_HEADER
#endif
#ifndef LPX4_ARCH
#if defined(__AVR_ARCH__) && __AVR_ARCH__ == 5
#define LPX4_ARCH LPX4_ARCH_AVR5
#else
#define LPX4_ARCH LPX4_ARCH_GENERIC
#endif
#endif
#ifndef LPX4_ENABLE_ASM
#define LPX4_ENABLE_ASM 0
#endif
#if LPX4_ENABLE_ASM != 0 && LPX4_ENABLE_ASM != 1
#error LPX4_ENABLE_ASM must be 0 or 1
#endif
#ifdef LPX4_USE_AVR_ASM
#error Select LPX4_ARCH and LPX4_ENABLE_ASM instead of the internal selector
#endif
#if LPX4_ARCH == LPX4_ARCH_AVR5 && LPX4_ENABLE_ASM && defined(__AVR__) && \
    defined(__AVR_ARCH__) && __AVR_ARCH__ == 5 && defined(__AVR_HAVE_MUL__) && \
    !defined(__AVR_TINY__) && defined(__GNUC__) && !defined(__clang__)
#define LPX4_USE_AVR_ASM 1
#else
#define LPX4_USE_AVR_ASM 0
#endif

// Byte-aligned shifts avoid a 12/14-iteration 32-bit shift loop at AVR -Os.
// The low byte cannot affect a floor right shift. Restore sign after 24 bits.
#define LPX4_SHIFT_BODY(N) \
    "mov %A0,%B0\n\tmov %B0,%C0\n\tmov %C0,%D0\n\t" \
    ".rept " #N "\n\tasr %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t" \
    "lsl %D0\n\tsbc %D0,%D0\n\t"
static inline __attribute__((always_inline)) int32_t lpx4Shift12(int32_t v){
#if LPX4_USE_AVR_ASM
    __asm__(LPX4_SHIFT_BODY(4) : "+r"(v) : : "cc");
    return v;
#else
    return v>>12;
#endif
}
static inline __attribute__((always_inline)) int32_t lpx4Shift14(int32_t v){
#if LPX4_USE_AVR_ASM
    __asm__(LPX4_SHIFT_BODY(6) : "+r"(v) : : "cc");
    return v;
#else
    return v>>14;
#endif
}
#undef LPX4_SHIFT_BODY

static inline __attribute__((always_inline)) int32_t lpx4Mul16(int16_t x,int16_t y){
#if LPX4_USE_AVR_ASM
    int32_t result;
    __asm__(
        "clr r2\n\tmuls %B1,%B2\n\tmovw %C0,r0\n\t"
        "mul %A1,%A2\n\tmovw %A0,r0\n\t"
        "mulsu %B1,%A2\n\tsbc %D0,r2\n\t"
        "add %B0,r0\n\tadc %C0,r1\n\tadc %D0,r2\n\t"
        "mulsu %B2,%A1\n\tsbc %D0,r2\n\t"
        "add %B0,r0\n\tadc %C0,r1\n\tadc %D0,r2\n\t"
        "clr __zero_reg__\n\t"
        : "=&r"(result) : "a"(x),"a"(y) : "r0","r1","r2","cc");
    return result;
#else
    return (int32_t)x*y;
#endif
}

// Exact per-product floor is part of Q0. The reverse traversal also shifts
// history in place: each old sample is consumed before its successor is written.
// Ten signed 20-bit products fit a signed 24-bit accumulator. The multiply's
// partial-product carry pattern follows AVR201 / Speex avr_multiply.h; this
// unrolled history traversal and per-product shift are LPX-specific.
#define LPX4_DOT_MUL \
    "muls r19,r21\n\tmovw r24,r0\n\t" \
    "mul r18,r20\n\tmovw r22,r0\n\t" \
    "mulsu r19,r20\n\tsbc r25,r16\n\t" \
    "add r23,r0\n\tadc r24,r1\n\tadc r25,r16\n\t" \
    "mulsu r21,r18\n\tsbc r25,r16\n\t" \
    "add r23,r0\n\tadc r24,r1\n\tadc r25,r16\n\t" \
    ".rept 4\n\tasr r25\n\tror r24\n\tror r23\n\t.endr\n\t" \
    "add %A0,r23\n\tadc %B0,r24\n\tadc %C0,r25\n\t"
static inline int32_t lpx4DotQ12(const int16_t* a,int16_t* h){
#if LPX4_USE_AVR_ASM
    int32_t result;
    a+=10;h+=10;
    __asm__ (
        "clr %A0\n\tclr %B0\n\tclr %C0\n\tclr r16\n\t"
        "ld r19,-X\n\tld r18,-X\n\tld r21,-Z\n\tld r20,-Z\n\t"
        LPX4_DOT_MUL
        ".rept 9\n\t"
        "ld r19,-X\n\tld r18,-X\n\tld r21,-Z\n\tld r20,-Z\n\t"
        "std Z+2,r20\n\tstd Z+3,r21\n\t"
        LPX4_DOT_MUL
        ".endr\n\t"
        "mov %D0,%C0\n\tlsl %D0\n\tsbc %D0,%D0\n\t"
        "clr __zero_reg__\n\t"
        : "=&r" (result), "+z" (h), "+x" (a)
        :
        : "r0","r1","r16","r18","r19","r20","r21",
          "r22","r23","r24","r25","cc","memory"
    );
    return result;
#else
    int32_t result=0;
    for(int8_t i=9;i>=0;i--){
        result+=((int32_t)a[i]*h[i])>>12;
        if(i<9)h[i+1]=h[i];
    }
    return result;
#endif
}
#undef LPX4_DOT_MUL

static inline __attribute__((always_inline)) int32_t lpx4MulQ14(int16_t x,int16_t y){
#if LPX4_USE_AVR_ASM
    int32_t result;
    __asm__ (
        "clr r2\n\tmuls %B1,%B2\n\tmovw %C0,r0\n\t"
        "mul %A1,%A2\n\tmovw %A0,r0\n\t"
        "mulsu %B1,%A2\n\tsbc %D0,r2\n\t"
        "add %B0,r0\n\tadc %C0,r1\n\tadc %D0,r2\n\t"
        "mulsu %B2,%A1\n\tsbc %D0,r2\n\t"
        "add %B0,r0\n\tadc %C0,r1\n\tadc %D0,r2\n\t"
        "mov %A0,%B0\n\tmov %B0,%C0\n\tmov %C0,%D0\n\t"
        ".rept 6\n\tasr %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        "lsl %D0\n\tsbc %D0,%D0\n\tclr __zero_reg__\n\t"
        : "=&r" (result) : "a" (x), "a" (y) : "r0","r1","r2","cc"
    );
    return result;
#else
    return ((int32_t)x*y)>>14;
#endif
}
