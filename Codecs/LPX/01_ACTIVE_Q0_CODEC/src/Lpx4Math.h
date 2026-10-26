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
#ifndef LPX4_AVR_DOT_UNROLL
#define LPX4_AVR_DOT_UNROLL 9
#endif
#if LPX4_AVR_DOT_UNROLL!=1 && LPX4_AVR_DOT_UNROLL!=3 && LPX4_AVR_DOT_UNROLL!=9
#error LPX4_AVR_DOT_UNROLL must be 1, 3 or 9
#endif

// Validated LSF10 values are 0..1023, anchor t is 0..16. Each intermediate
// fits signed16: prev*16 + (cur-prev)*t is a convex weighted sum, 0..16368.
static inline __attribute__((always_inline)) uint16_t lpx4LsfNorm10(int16_t prev,int16_t cur,uint8_t t){
    const int16_t delta=(int16_t)(cur-prev);
    const int16_t weighted=(int16_t)(prev*16+delta*t);
    return ((uint16_t)weighted)>>2;
}
// Adjacent retained Q13 cosine nodes differ by at most 101; fraction is 0..15.
// The signed16 product fits (-1515..0), retaining the original floor shift.
static inline __attribute__((always_inline)) int16_t lpx4CosineInterpolate(int16_t lo,int16_t hi,uint8_t fraction){
    const int16_t product=(int16_t)((hi-lo)*fraction);
    return (int16_t)(lo+(product>>4));
}

// Convex signed16 LPC anchors, t=0..2^bits, bits=2/3/4.
// Preserve prev + trunc((cur-prev)*t / 2^bits), including a signed17
// difference. The convex result already fits signed16; no clamp is needed.
static inline __attribute__((always_inline)) int16_t lpx4LpcInterpolate(int16_t prev,int16_t cur,uint8_t t,uint8_t bits){
#if LPX4_USE_AVR_ASM
    int32_t product;
    int16_t delta;
    uint8_t negative;
    __asm__(
        "clr %2\n\tmovw %A1,%A4\n\t"
        "sub %A1,%A3\n\tsbc %B1,%B3\n\tbrge 1f\n\tdec %2\n\t1:\n\t"
        // delta's low word is unsigned; negative differences subtract t<<16.
        "mul %A1,%5\n\tmovw %A0,r0\n\tclr %C0\n\t"
        "mul %B1,%5\n\tadd %B0,r0\n\tadc %C0,r1\n\t"
        "sbrc %2,7\n\tsub %C0,%5\n\tclr __zero_reg__\n\t"
        // Bias only negative products to retain division toward zero.
        "andi %2,%6\n\tadd %A0,%2\n\tadc %B0,__zero_reg__\n\tadc %C0,__zero_reg__\n\t"
        ".rept %7\n\tasr %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        "add %A0,%A3\n\tadc %B0,%B3\n\t"
        : "=&r"(product),"=&r"(delta),"=&d"(negative)
        : "r"(prev),"r"(cur),"r"(t),"M"((1U<<bits)-1),"I"(bits)
        : "r0","r1","cc");
    return (int16_t)product;
#else
    return (int16_t)(prev+((int32_t)cur-prev)*t/(1L<<bits));
#endif
}

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

// Exact signed8 x signed16 product. Both partial products fit signed24;
// keep the full signed16 x signed16 helper separate.
static inline __attribute__((always_inline)) int32_t lpx4Mul8x16(int8_t x,int16_t y){
#if LPX4_USE_AVR_ASM
    int32_t result;
    __asm__(
        "mulsu %1,%A2\n\tmovw %A0,r0\n\t"
        "mov %C0,r1\n\tlsl %C0\n\tsbc %C0,%C0\n\t"
        "muls %1,%B2\n\tadd %B0,r0\n\tadc %C0,r1\n\t"
        "mov %D0,%C0\n\tlsl %D0\n\tsbc %D0,%D0\n\t"
        "clr __zero_reg__\n\t"
        : "=&r"(result) : "a"(x),"a"(y) : "r0","r1","cc");
    return result;
#else
    return (int32_t)x*y;
#endif
}

// Decoder excitation retains its narrower contract: step 0..4095
// (actual retained scales 0..4016), so the signed16 cast is lossless.
static inline __attribute__((always_inline)) int32_t lpx4Excitation(int8_t x,uint16_t step){
    return lpx4Mul8x16(x,(int16_t)step);
}

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
#define LPX4_DOT_PRODUCT_BYTES \
    "muls r19,r21\n\tmovw r24,r0\n\t" \
    "mul r18,r20\n\tmovw r22,r0\n\t" \
    "mulsu r19,r20\n\tsbc r25,r16\n\t" \
    "add r23,r0\n\tadc r24,r1\n\tadc r25,r16\n\t" \
    "mulsu r21,r18\n\tsbc r25,r16\n\t" \
    "add r23,r0\n\tadc r24,r1\n\tadc r25,r16\n\t"
#define LPX4_DOT_PRODUCT LPX4_DOT_PRODUCT_BYTES \
    ".rept 4\n\tasr r25\n\tror r24\n\tror r23\n\t.endr\n\t"
#define LPX4_DOT_MUL LPX4_DOT_PRODUCT \
    "add %A0,r23\n\tadc %B0,r24\n\tadc %C0,r25\n\t"
#define LPX4_STRING_(V) #V
#define LPX4_STRING(V) LPX4_STRING_(V)
static inline int32_t lpx4DotQ12(const int16_t* a,int16_t* h){
#if LPX4_USE_AVR_ASM
    int32_t result;
    a+=10;h+=10;
    __asm__ (
        "clr %A0\n\tclr %B0\n\tclr %C0\n\tclr r16\n\t"
        "ld r19,-X\n\tld r18,-X\n\tld r21,-Z\n\tld r20,-Z\n\t"
        LPX4_DOT_MUL
#if LPX4_AVR_DOT_UNROLL!=9
        "ldi r17," LPX4_STRING(9/LPX4_AVR_DOT_UNROLL) "\n\t1:\n\t"
#endif
        ".rept " LPX4_STRING(LPX4_AVR_DOT_UNROLL) "\n\t"
        "ld r19,-X\n\tld r18,-X\n\tld r21,-Z\n\tld r20,-Z\n\t"
        "std Z+2,r20\n\tstd Z+3,r21\n\t"
        LPX4_DOT_MUL
        ".endr\n\t"
#if LPX4_AVR_DOT_UNROLL!=9
        "dec r17\n\tbreq 2f\n\trjmp 1b\n\t2:\n\t"
#endif
        "mov %D0,%C0\n\tlsl %D0\n\tsbc %D0,%D0\n\t"
        "clr __zero_reg__\n\t"
        : "=&r" (result), "+z" (h), "+x" (a)
        :
        : "r0","r1","r16","r18","r19","r20","r21",
#if LPX4_AVR_DOT_UNROLL!=9
          "r17",
#endif
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
// Exact excitation minus individually rounded Q12 products, with history shift.
// Precondition: |excitation| <= 524288 (covers signed8 x unsigned12).
// Ten full-range signed16 products plus excitation fit signed24, including
// every intermediate subtraction. The AVR Q4 accumulator needs signed27,
// fits signed32, and divides by 16 once. Clipping remains the final step.
// Clear each product's Q4 fractional nibble before subtraction. This keeps
// every original per-product floor, but defers the accumulator's /16 until
// after all ten products. Its low nibble remains zero throughout the sum.
#define LPX4_SYNTH_MUL LPX4_DOT_PRODUCT_BYTES \
    "andi r23,0xf0\n\t" \
    "sub %A0,r23\n\tsbc %B0,r24\n\tsbc %C0,r25\n\tsbc %D0,r16\n\t" \
    "sbrc r25,7\n\tinc %D0\n\t"
static inline int32_t lpx4SynthesisQ12(int32_t excitation,const int16_t* a,int16_t* h){
#if LPX4_USE_AVR_ASM
    int32_t result=excitation;
    a+=10;h+=10;
    __asm__ (
        "clr r16\n\t"
        ".rept 4\n\tlsl %A0\n\trol %B0\n\trol %C0\n\trol %D0\n\t.endr\n\t"
        "ld r19,-X\n\tld r18,-X\n\tld r21,-Z\n\tld r20,-Z\n\t"
        LPX4_SYNTH_MUL
#if LPX4_AVR_DOT_UNROLL!=9
        "ldi r17," LPX4_STRING(9/LPX4_AVR_DOT_UNROLL) "\n\t1:\n\t"
#endif
        ".rept " LPX4_STRING(LPX4_AVR_DOT_UNROLL) "\n\t"
        "ld r19,-X\n\tld r18,-X\n\tld r21,-Z\n\tld r20,-Z\n\t"
        "std Z+2,r20\n\tstd Z+3,r21\n\t"
        LPX4_SYNTH_MUL
        ".endr\n\t"
#if LPX4_AVR_DOT_UNROLL!=9
        "dec r17\n\tbreq 2f\n\trjmp 1b\n\t2:\n\t"
#endif
        ".rept 4\n\tasr %D0\n\tror %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        "clr __zero_reg__\n\t"
        : "+&r" (result), "+z" (h), "+x" (a)
        :
        : "r0","r1","r16","r18","r19","r20","r21",
#if LPX4_AVR_DOT_UNROLL!=9
          "r17",
#endif
          "r22","r23","r24","r25","cc","memory"
    );
    return result;
#else
    int32_t result=excitation;
    for(int8_t i=9;i>=0;i--){
        result-=((int32_t)a[i]*h[i])>>12;
        if(i<9)h[i+1]=h[i];
    }
    return result;
#endif
}
// Same exact sum, read-only mirrored history. h points just past ten old
// samples in reverse temporal order; return it advanced back by ten words.
// The caller then writes the new sample to h[0] and h[10]. Preconditions and
// Q4 bounds match SynthesisQ12; this helper never shifts/stores old samples.
static inline __attribute__((always_inline)) int32_t lpx4SynthesisRingQ12(int32_t excitation,const int16_t* a,int16_t*& h){
#if LPX4_USE_AVR_ASM
    int32_t result=excitation;
    __asm__ (
        "clr r16\n\t"
        ".rept 4\n\tlsl %A0\n\trol %B0\n\trol %C0\n\trol %D0\n\t.endr\n\t"
        "ld r18,X+\n\tld r19,X+\n\tld r21,-Z\n\tld r20,-Z\n\t"
        LPX4_SYNTH_MUL
#if LPX4_AVR_DOT_UNROLL!=9
        "ldi r17," LPX4_STRING(9/LPX4_AVR_DOT_UNROLL) "\n\t1:\n\t"
#endif
        ".rept " LPX4_STRING(LPX4_AVR_DOT_UNROLL) "\n\t"
        "ld r18,X+\n\tld r19,X+\n\tld r21,-Z\n\tld r20,-Z\n\t"
        LPX4_SYNTH_MUL
        ".endr\n\t"
#if LPX4_AVR_DOT_UNROLL!=9
        "dec r17\n\tbreq 2f\n\trjmp 1b\n\t2:\n\t"
#endif
        ".rept 4\n\tasr %D0\n\tror %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        "clr __zero_reg__\n\t"
        : "+&r" (result), "+z" (h), "+x" (a)
        :
        : "r0","r1","r16","r18","r19","r20","r21",
#if LPX4_AVR_DOT_UNROLL!=9
          "r17",
#endif
          "r22","r23","r24","r25","cc","memory"
    );
    return result;
#else
    int32_t result=excitation;
    for(uint8_t i=0;i<10;i++)result-=((int32_t)a[i]*h[-1-i])>>12;
    h-=10;
    return result;
#endif
}
#undef LPX4_SYNTH_MUL
#undef LPX4_DOT_PRODUCT
#undef LPX4_DOT_PRODUCT_BYTES
#undef LPX4_DOT_MUL
#undef LPX4_STRING
#undef LPX4_STRING_

// Saturate a signed24 value to the synthesis range -32767..32767.
// Synthesis is bounded by +/-3145728, so its upper byte is sign extension.
static inline __attribute__((always_inline)) int16_t lpx4Clip15From24(int32_t value){
#if LPX4_USE_AVR_ASM
    int16_t result;
    __asm__(
        // Compare byte C to the sign of the low word, then restore byte B.
        "lsl %B1\n\tsbc %A0,%A0\n\tcp %C1,%A0\n\tbrne 1f\n\t"
        "lsl %A0\n\tror %B1\n\tmovw %A0,%A1\n\t"
        // The exact signed16 minimum is excluded from the synthesis range.
        "cpi %B0,128\n\tbrne 2f\n\ttst %A0\n\tbrne 2f\n\t"
        "inc %A0\n\trjmp 2f\n\t"
        "1:\n\tldi %A0,255\n\tldi %B0,127\n\tsbrs %C1,7\n\trjmp 2f\n\t"
        "ldi %A0,1\n\tldi %B0,128\n\t2:\n\t"
        : "=&d"(result),"+r"(value) : : "cc");
    return result;
#else
    return value<-32767?-32767:(value>32767?32767:(int16_t)value);
#endif
}

// Full signed16 addition with the same non-minimum saturation range.
static inline __attribute__((always_inline)) int16_t lpx4AddClip15(int16_t a,int16_t b){
#if LPX4_USE_AVR_ASM
    __asm__(
        "add %A0,%A1\n\tadc %B0,%B1\n\tbrvc 1f\n\tbrmi 2f\n\t"
        // Negative overflow has a nonnegative wrapped sum; positive reverses it.
        "ldi %A0,1\n\tldi %B0,128\n\trjmp 3f\n\t"
        "2:\n\tldi %A0,255\n\tldi %B0,127\n\trjmp 3f\n\t"
        "1:\n\tcpi %B0,128\n\tbrne 3f\n\ttst %A0\n\tbrne 3f\n\t"
        "inc %A0\n\t3:\n\t"
        : "+&d"(a) : "r"(b) : "cc");
    return a;
#else
    const int32_t sum=(int32_t)a+b;
    return sum<-32767?-32767:(sum>32767?32767:(int16_t)sum);
#endif
}

static inline __attribute__((always_inline)) int16_t lpx4ClipQ14(int16_t value){
    return value<-16384?-16384:(value>16384?16384:value);
}

// Rounded legacy PWM, exact for signed16 sample and gain 0..255.
// floor((sample*gain+8192)/16384)+128, saturated to uint8.
static inline __attribute__((always_inline)) uint8_t lpx4PwmQ14(int16_t sample,uint8_t gain){
#if LPX4_USE_AVR_ASM
    uint8_t result;
    int16_t high;
    __asm__(
        "clr %0\n\t"
        "mulsu %B2,%3\n\tmovw %A1,r0\n\t"
        "mul %A2,%3\n\tadd %A1,r1\n\tadc %B1,%0\n\t"
        // The discarded product low byte cannot affect the Q14 quotient.
        "subi %A1,224\n\tsbci %B1,255\n\t"
        ".rept 6\n\tasr %B1\n\tror %A1\n\t.endr\n\t"
        "subi %A1,128\n\tsbci %B1,255\n\t"
        "mov %0,%A1\n\ttst %B1\n\tbreq 1f\n\t"
        "ldi %0,255\n\tsbrc %B1,7\n\tclr %0\n\t1:\n\t"
        "clr __zero_reg__\n\t"
        : "=&d"(result),"=&a"(high) : "a"(sample),"a"(gain) : "r0","r1","cc");
    return result;
#else
    const int32_t duty=128+(((int32_t)sample*gain+8192)>>14);
    return duty<0?0:(duty>255?255:(uint8_t)duty);
#endif
}

// Bounded attenuation: coefficient 0..16384, signed16 state, exact floor Q14.
// The result fits signed16. Keep the generic full-range MulQ14 below.
static inline __attribute__((always_inline)) int16_t lpx4AttenuateQ14(uint16_t coefficient,int16_t state){
#if LPX4_USE_AVR_ASM
    int16_t result;
    int32_t wide;
    __asm__(
        "clr %A0\n\t"
        "muls %B2,%B3\n\tmovw %C1,r0\n\t"
        "mul %A2,%A3\n\tmovw %A1,r0\n\t"
        // coefficient high <=64: its product with state low has bit15 clear.
        "mulsu %B2,%A3\n\t"
        "add %B1,r0\n\tadc %C1,r1\n\tadc %D1,%A0\n\t"
        "mulsu %B3,%A2\n\tsbc %D1,%A0\n\t"
        "add %B1,r0\n\tadc %C1,r1\n\tadc %D1,%A0\n\t"
        // Bits 14..29 are the entire signed16 result: shift left twice and
        // take the high word, avoiding six 24-bit arithmetic right shifts.
        ".rept 2\n\tlsl %B1\n\trol %C1\n\trol %D1\n\t.endr\n\t"
        "movw %A0,%C1\n\tclr __zero_reg__\n\t"
        : "=&r"(result),"=&r"(wide) : "a"(coefficient),"a"(state) : "r0","r1","cc");
    return result;
#else
    return (int16_t)(((int32_t)coefficient*state)>>14);
#endif
}

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
