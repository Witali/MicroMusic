#pragma once
#include <stdint.h>

// Optional platform header may select an architecture and arithmetic backend.
// Memory access remains controlled by the compiler's real __AVR__ macro.
#define LPX4_ARCH_GENERIC 0
#define LPX4_ARCH_AVR5 1
#define LPX4_ARCH_AVR25 2
#ifdef LPX4_PLATFORM_HEADER
#include LPX4_PLATFORM_HEADER
#endif
#ifndef LPX4_ARCH
#if defined(__AVR_ARCH__) && __AVR_ARCH__ == 5
#define LPX4_ARCH LPX4_ARCH_AVR5
#elif defined(__AVR_ARCH__) && __AVR_ARCH__ == 25
#define LPX4_ARCH LPX4_ARCH_AVR25
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
#if defined(LPX4_USE_AVR_ASM) || defined(LPX4_USE_AVR_NOMUL_ASM)
#error Select LPX4_ARCH and LPX4_ENABLE_ASM instead of the internal selector
#endif
#if LPX4_ARCH == LPX4_ARCH_AVR5 && LPX4_ENABLE_ASM && defined(__AVR__) && \
    defined(__AVR_ARCH__) && __AVR_ARCH__ == 5 && defined(__AVR_HAVE_MUL__) && \
    !defined(__AVR_TINY__) && defined(__GNUC__) && !defined(__clang__)
#define LPX4_USE_AVR_ASM 1
#else
#define LPX4_USE_AVR_ASM 0
#endif
#if LPX4_ARCH == LPX4_ARCH_AVR25 && LPX4_ENABLE_ASM && defined(__AVR__) && \
    defined(__AVR_ARCH__) && __AVR_ARCH__ == 25 && !defined(__AVR_HAVE_MUL__) && \
    !defined(__AVR_TINY__) && defined(__GNUC__) && !defined(__clang__)
#define LPX4_USE_AVR_NOMUL_ASM 1
#else
#define LPX4_USE_AVR_NOMUL_ASM 0
#endif
#ifndef LPX4_AVR_DOT_UNROLL
#define LPX4_AVR_DOT_UNROLL 9
#endif
#if LPX4_AVR_DOT_UNROLL!=1 && LPX4_AVR_DOT_UNROLL!=3 && LPX4_AVR_DOT_UNROLL!=9
#error LPX4_AVR_DOT_UNROLL must be 1, 3 or 9
#endif
// AVR25 software signed16 multiplication: keep the original fully unrolled
// default; an explicit smaller group trades loop-latch cycles for Flash.
#ifndef LPX4_AVR25_MUL16_UNROLL
#define LPX4_AVR25_MUL16_UNROLL 16
#endif
#if LPX4_AVR25_MUL16_UNROLL!=1 && LPX4_AVR25_MUL16_UNROLL!=2 && \
    LPX4_AVR25_MUL16_UNROLL!=4 && LPX4_AVR25_MUL16_UNROLL!=8 && LPX4_AVR25_MUL16_UNROLL!=16
#error LPX4_AVR25_MUL16_UNROLL must be 1, 2, 4, 8 or 16
#endif
#ifndef LPX4_AVR25_SATURATED_PRODUCTS
#define LPX4_AVR25_SATURATED_PRODUCTS 0
#endif
#if LPX4_AVR25_SATURATED_PRODUCTS != 0 && LPX4_AVR25_SATURATED_PRODUCTS != 1
#error LPX4_AVR25_SATURATED_PRODUCTS must be 0 or 1
#endif

static inline int32_t lpx4Mul32x16(int32_t x,int16_t y);
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
template<bool oddPhase=false>
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
#elif LPX4_USE_AVR_NOMUL_ASM
    if(oddPhase){
        // The signed comparison after SBC handles a 17-bit difference.
        // Its magnitude fits uint16_t. Start with the implicit low phase
        // bit, then rotate each unsigned addition's carry into the result.
        // Add or subtract the truncated magnitude from the previous anchor.
        uint16_t part,mag=(uint16_t)cur;
        t>>=1;
        __asm__(
            "clt\n\tsub %A1,%A3\n\tsbc %B1,%B3\n\t"
            "brge 1f\n\tset\n\tcom %B1\n\tneg %A1\n\tsbci %B1,255\n\t"
            "1: movw %A0,%A1\n\tlsr %B0\n\tror %A0\n\t"
            ".rept %4-1\n\tlsr %2\n\tbrcc 2f\n\t"
            "add %A0,%A1\n\tadc %B0,%B1\n\t"
            "2: ror %B0\n\tror %A0\n\t.endr\n\t"
            "brtc 3f\n\tsub %A3,%A0\n\tsbc %B3,%B0\n\trjmp 4f\n\t"
            "3: add %A3,%A0\n\tadc %B3,%B0\n\t4:\n\t"
            : "=&d"(part),"+&d"(mag),"+&r"(t),"+&r"(prev) : "I"(bits) : "cc");
        return prev;
    }
    int32_t delta=(int32_t)cur-prev,product;
    uint8_t bias;
    __asm__(
        "clr %A0\n\tclr %B0\n\tclr %C0\n\t"
        "mov %3,%C1\n\tandi %3,%6\n\t"
        ".rept %5+1\n\tlsr %2\n\tbrcc 1f\n\t"
        "add %A0,%A1\n\tadc %B0,%B1\n\tadc %C0,%C1\n\t"
        "1: lsl %A1\n\trol %B1\n\trol %C1\n\t.endr\n\t"
        "add %A0,%3\n\tadc %B0,__zero_reg__\n\tadc %C0,__zero_reg__\n\t"
        ".rept %5\n\tasr %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        "add %A0,%A4\n\tadc %B0,%B4\n\t"
        : "=&r"(product),"+&r"(delta),"+&r"(t),"=&d"(bias)
        : "r"(prev),"I"(bits),"M"((1U<<bits)-1) : "cc");
    return (int16_t)product;
#else
    const int32_t product=((int32_t)cur-prev)*t;
    // Bias negative products so the arithmetic shift truncates toward zero.
    const int32_t bias=product<0?(1L<<bits)-1:0;
    return (int16_t)(prev+((product+bias)>>bits));
#endif
}

// Byte-aligned shifts avoid a 12/14-iteration 32-bit shift loop at AVR -Os.
// The low byte cannot affect a floor right shift. Restore sign after 24 bits.
#define LPX4_SHIFT_BODY(N) \
    "mov %A0,%B0\n\tmov %B0,%C0\n\tmov %C0,%D0\n\t" \
    ".rept " #N "\n\tasr %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t" \
    "lsl %D0\n\tsbc %D0,%D0\n\t"
static inline __attribute__((always_inline)) int32_t lpx4Shift12(int32_t v){
#if LPX4_USE_AVR_ASM || LPX4_USE_AVR_NOMUL_ASM
    __asm__(LPX4_SHIFT_BODY(4) : "+r"(v) : : "cc");
    return v;
#else
    return (int32_t)(int16_t)(v>>16)*16+((uint16_t)v>>12);
#endif
}
static inline __attribute__((always_inline)) int32_t lpx4Shift14(int32_t v){
#if LPX4_USE_AVR_ASM || LPX4_USE_AVR_NOMUL_ASM
    __asm__(LPX4_SHIFT_BODY(6) : "+r"(v) : : "cc");
    return v;
#else
    return (int32_t)(int16_t)(v>>16)*4+((uint16_t)v>>14);
#endif
}
#undef LPX4_SHIFT_BODY

// Exact floor of remainder*coefficient/4096 for remainder in -15..15
// and a Q12 cosine factor in -8192..8192.
static inline __attribute__((always_inline)) int8_t lpx4NibbleMulQ12(int8_t remainder,int16_t coefficient){
#if LPX4_USE_AVR_NOMUL_ASM
    uint16_t accum;
    uint8_t bits=(uint8_t)remainder;
    uint8_t correction=bits;
    // Four rounds give floor(unsigned nibble * uint16(coefficient) / 16).
    // If the coefficient is negative, subtract 4096*nibble. If the
    // remainder is negative, subtract the coefficient for its implicit -16.
    // Both corrections are integers at this scale. Extract the high byte
    // after both corrections to finish the arithmetic floor shift by 12.
    __asm__(
        "clr %A0\n\tclr %B0\n\t"
        ".rept 4\n\tlsr %1\n\tbrcc 1f\n\tadd %A0,%A3\n\tadc %B0,%B3\n\t"
        "1: ror %B0\n\tror %A0\n\t.endr\n\t"
        "swap %2\n\tandi %2,240\n\t"
        "sbrc %B3,7\n\tsub %B0,%2\n\t"
        "sbrs %1,3\n\trjmp 2f\n\tsub %A0,%A3\n\tsbc %B0,%B3\n\t2:\n\t"
        : "=&r"(accum),"+&r"(bits),"+&d"(correction)
        : "r"(coefficient) : "cc");
    return (int8_t)(accum>>8);
#else
    return (int8_t)(((int32_t)remainder*coefficient)>>12);
#endif
}

#if LPX4_USE_AVR_NOMUL_ASM
#define LPX4_MUL_INLINE __attribute__((noinline))
#else
#define LPX4_MUL_INLINE inline __attribute__((always_inline))
#endif
static LPX4_MUL_INLINE int32_t lpx4Mul16(int16_t x,int16_t y);

// Exact signed8 x signed16, signed8 x unsigned16 and signed16 x signed16.
// Parser, filters and memory access share these same C/ASM interfaces.
#if LPX4_USE_AVR_ASM || LPX4_USE_AVR_NOMUL_ASM
#include "Lpx4MultiplyAvr.h"
#else
#include "Lpx4MultiplyC.h"
#endif



// Pitch gain0..31, history code -32..31: rounded Q4 lies in -62..60.
// Extract product bits4..11 with two nibble swaps instead of 16-bit shifts.
static inline __attribute__((always_inline)) int8_t lpx4PitchQ4(int8_t x,uint8_t gain,bool evenGain=false){
#if LPX4_USE_AVR_ASM
    int16_t product;
    __asm__(
        "muls %1,%2\n\tmovw %A0,r0\n\tclr __zero_reg__\n\t"
        "subi %A0,248\n\tsbci %B0,255\n\t"
        "swap %A0\n\tandi %A0,15\n\tswap %B0\n\tandi %B0,240\n\tor %A0,%B0\n\t"
        : "=&d"(product) : "a"(x),"a"(gain) : "r0","r1","cc");
    return (int8_t)product;
#elif LPX4_USE_AVR_NOMUL_ASM
    // Common exact v5 gains. In particular gain14 has stable +/-3 feedback,
    // so avoiding a software product also helps dense voiced excitation.
    if(gain==14){
        // 4-x is signed9 for the full signed8 domain. V marks its rare
        // positive overflow; one logical shift restores the exact sign.
        int8_t correction;
        __asm__(
            "ldi %1,4\n\tsub %1,%0\n\tbrvc 1f\n\t"
            "lsr %1\n\trjmp 2f\n\t1: asr %1\n\t"
            "2: asr %1\n\tasr %1\n\tadd %0,%1\n\t"
            : "+r"(x),"=&d"(correction) : : "cc");
        return x;
    }
    if(!gain)return 0;
    // Four rounds give the Q4 quotient directly in one byte. Compact speech
    // gain is even and <=14, so its equivalent Q3 quotient takes three rounds.
    // Remove the unsigned-history bias using the original gain in both cases.
    uint8_t result,multiplier;
    __asm__(
        "ldi %0,%5\n\tmov %1,%2\n\t"
        ".if %4\n\tlsr %1\n\t.endif\n\t"
        ".rept 4-%4\n\tlsr %1\n\tbrcc 1f\n\tadd %0,%3\n\t1: ror %0\n\t.endr\n\t"
        ".if !%4\n\tsbrc %1,0\n\tadd %0,%3\n\t.endif\n\t"
        "swap %2\n\tandi %2,240\n\tsbrc %3,7\n\tsub %0,%2\n\t"
        : "=&d"(result),"=&r"(multiplier),"+&d"(gain)
        : "r"(x),"I"(evenGain),"I"(evenGain?4:8) : "cc");
    return (int8_t)result;
#else
    return (int8_t)(((int16_t)x*gain+8)>>4);
#endif
}

// Decoder excitation retains its narrower contract: step 0..4095
// (actual retained scales 0..4016), so the signed16 cast is lossless.
static inline __attribute__((always_inline)) int32_t lpx4Excitation(int8_t x,uint16_t step){
    return lpx4Mul8x16(x,(int16_t)step);
}


// Low 32 bits of a signed32 x signed16 product. The decoder checks the
// polynomial bound before calling; modular decomposition avoids signed UB.
static inline int32_t lpx4Mul32x16(int32_t x,int16_t y){
#if LPX4_USE_AVR_NOMUL_ASM
    const int16_t low=(int16_t)x;
    const int16_t high=(int16_t)((x>>16)+(low<0));
    const int16_t upper=high==0?0:high==1?y:high==-1?(int16_t)(0U-(uint16_t)y):
        (int16_t)((uint32_t)(uint16_t)high*(uint16_t)y);
    return (int32_t)((uint32_t)lpx4Mul16(low,y)+((uint32_t)(uint16_t)upper<<16));
#else
    return (int32_t)((uint32_t)x*(uint32_t)(int32_t)y);
#endif
}

// The direct LPC polynomial product has |value| <= 250000 and
// |coefficient| <= 8192. The signed low word leaves only -4..4 in the
// upper part. A zero upper part needs no correction to the low product.
static inline __attribute__((always_inline)) int32_t lpx4BoundedPolyQ12(int32_t value,int16_t coefficient){
#if LPX4_USE_AVR_NOMUL_ASM
    const int16_t low=(int16_t)value;
    const int8_t high=(int8_t)((value>>16)+(low<0));
    const int32_t product=lpx4Mul16(low,coefficient);
    if(!high)return lpx4Shift12(product);

    uint16_t correction;
    uint8_t multiplier=(uint8_t)high;
    uint16_t operand=(uint16_t)coefficient;
    __asm__(
        "clr %A0\n\tclr %B0\n\t"
        "sbrs %1,7\n\trjmp 1f\n\t"
        "neg %1\n\tcom %B2\n\tneg %A2\n\tsbci %B2,255\n\t"
        "1: lsr %1\n\tbrcc 2f\n\tmovw %A0,%A2\n\t"
        "2: breq 3f\n\tlsl %A2\n\trol %B2\n\tlsr %1\n\tbrcc 2b\n\t"
        "add %A0,%A2\n\tadc %B0,%B2\n\ttst %1\n\tbrne 2b\n\t3:\n\t"
        : "=&w"(correction),"+&r"(multiplier),"+&d"(operand) : : "cc");
    return lpx4Shift12((int32_t)((uint32_t)product+((uint32_t)correction<<16)));
#else
    return lpx4Shift12(value*coefficient);
#endif
}

// Exact per-product floor is part of Q0. The reverse traversal also shifts
// history in place: each old sample is consumed before its successor is written.
// Ten signed 20-bit products fit a signed 24-bit accumulator. The multiply's
// partial-product carry pattern follows AVR201 / Speex avr_multiply.h; this
// unrolled history traversal and per-product shift are LPX-specific.
#define LPX4_LPC_LOAD_REVERSE "ld r19,-X\n\tld r18,-X\n\tld r21,-Z\n\tld r20,-Z\n\t"
#define LPX4_LPC_SHIFT_HISTORY "std Z+2,r20\n\tstd Z+3,r21\n\t"
#if LPX4_COMPACT_VERSION==9
#define LPX4_DOT_LOW_RESULT "mov r23,r1\n\t"
#define LPX4_DOT_LOW_CLOBBER
#else
#define LPX4_DOT_LOW_RESULT "movw r22,r0\n\t"
#define LPX4_DOT_LOW_CLOBBER "r22",
#endif
#define LPX4_DOT_PRODUCT_BYTES \
    "muls r19,r21\n\tmovw r24,r0\n\t" \
    "mul r18,r20\n\t" LPX4_DOT_LOW_RESULT \
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
        LPX4_LPC_LOAD_REVERSE
        LPX4_DOT_MUL
#if LPX4_AVR_DOT_UNROLL!=9
        "ldi r17," LPX4_STRING(9/LPX4_AVR_DOT_UNROLL) "\n\t1:\n\t"
#endif
        ".rept " LPX4_STRING(LPX4_AVR_DOT_UNROLL) "\n\t"
        LPX4_LPC_LOAD_REVERSE
        LPX4_LPC_SHIFT_HISTORY
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
          LPX4_DOT_LOW_CLOBBER "r23","r24","r25","cc","memory"
    );
    return result;
#else
    int32_t result=0;
    for(int8_t i=9;i>=0;i--){
        result+=lpx4Shift12(lpx4Mul16(a[i],h[i]));
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
#if LPX4_COMPACT_VERSION==9
// Toggle bit 23 to represent each signed term as unsigned with a bias of
// 2^23. Add the ten biases once (10 * 2^23 == 0x05000000) to compensate.
#define LPX4_SYNTH_INIT "ldi r25,5\n\tadd %D0,r25\n\t"
#define LPX4_SYNTH_MUL LPX4_DOT_PRODUCT_BYTES \
    "andi r23,0xf0\n\tsubi r25,128\n\t" \
    "sub %A0,r23\n\tsbc %B0,r24\n\tsbc %C0,r25\n\tsbc %D0,r16\n\t"
#else
#define LPX4_SYNTH_INIT ""
#define LPX4_SYNTH_MUL LPX4_DOT_PRODUCT_BYTES \
    "andi r23,0xf0\n\t" \
    "sub %A0,r23\n\tsbc %B0,r24\n\tsbc %C0,r25\n\tsbc %D0,r16\n\t" \
    "sbrc r25,7\n\tinc %D0\n\t"
#endif
#define LPX4_NOMUL_HIGH_STEP \
    "lsr r22\n\tbrcc 3f\n\tadd r24,r18\n\tadc r25,r19\n\t" \
    "3: ror r25\n\tror r24\n\t"
// Q12 needs only product bits12..31. Shift a separate multiplier byte;
// capture outgoing product bits only in the final four rounds. No discarded
// low product byte is ever computed. r23's low nibble is immaterial.
#if LPX4_AVR25_SATURATED_PRODUCTS
// For h=32767: floor(a*h/256)=128*a-ceil(a/256).
// For h=-32767: floor(a*h/256)=-128*a+floor(a/256).
// With boundedLpc, negating a for the negative rail is safe and shares
// the positive-rail formula. The subsequent nibble mask keeps the Q12 floor.
// T is a private hint; skipping this route still uses the exact general product.
#define LPX4_NOMUL_SATURATED \
    "brtc 11f\n\tcpi r21,127\n\tbrne 10f\n\tcpi r20,255\n\tbreq 12f\n\t" \
    "10: cpi r21,128\n\tbrne 11f\n\tcpi r20,1\n\tbrne 11f\n\t" \
    ".if %7\n\t" \
    "12: sbrs r21,7\n\trjmp 13f\n\t" \
    "com r19\n\tneg r18\n\tsbci r19,255\n\t13:\n\t" \
    "movw r24,r18\n\tclr r23\n\tasr r25\n\tror r24\n\tror r23\n\t" \
    "clr r20\n\tsbrc r19,7\n\tdec r20\n\t" \
    "cp __zero_reg__,r18\n\tsbc r23,r19\n\tsbc r24,r20\n\tsbc r25,r20\n\trjmp 8f\n\t11:\n\t" \
    ".else\n\t" \
    "12: mov r24,r18\n\tmov r25,r19\n\tclr r23\n\t" \
    "asr r25\n\tror r24\n\tror r23\n\t" \
    "clr r20\n\tsbrc r19,7\n\tdec r20\n\t" \
    "cp __zero_reg__,r18\n\tsbrc r21,7\n\tclc\n\t" \
    "sbc r23,r19\n\tsbc r24,r20\n\tsbc r25,r20\n\t" \
    "sbrs r21,7\n\trjmp 8f\n\t" \
    "com r25\n\tcom r24\n\tneg r23\n\tsbci r24,255\n\tsbci r25,255\n\trjmp 8f\n\t11:\n\t" \
    ".endif\n\t" \
    ""
#else
#define LPX4_NOMUL_SATURATED ""
#endif
#if LPX4_AVR25_SATURATED_PRODUCTS
// In the full-width path, r23 starts as the history high byte. Each
// rotation supplies the next multiplier bit through carry and replaces the
// consumed bit with product bits. A pair needs no separate multiplier shift.
#define LPX4_NOMUL_LPC_BIT \
    "brcc 3f\n\tadd r24,r18\n\tadc r25,r19\n\t" \
    "3: ror r25\n\tror r24\n\tror r23\n\t"
#define LPX4_NOMUL_LPC_PAIR \
    LPX4_NOMUL_LPC_BIT LPX4_NOMUL_LPC_BIT
// Split h into its unsigned low byte and signed high byte. For a small
// high byte (-8..7), a few exact 24-bit additions replace eight multiply
// rounds. B=floor(uint16(a)*lo(h)/256), then B+uint16(a)*int8(hi(h)).
// For negative a, subtract 256*h. Every intermediate fits signed24;
// the existing Q4 nibble mask preserves each separate Q12 floor.
#define LPX4_NOMUL_PRODUCT \
    /* Test both history bytes while keeping the low byte in r22. */ \
    "movw r22,r20\n\tor r23,r22\n\tbrne 18f\n\trjmp 5f\n\t18:\n\t" \
    LPX4_NOMUL_SATURATED \
    "clr r24\n\tclr r25\n\t" \
    /* The first unsigned round is either zero or half the coefficient. */ \
    "lsr r22\n\tbrcc 3f\n\tmovw r24,r18\n\tlsr r25\n\tror r24\n\t3:\n\t" \
    ".rept 7\n\t" LPX4_NOMUL_HIGH_STEP ".endr\n\t" \
    "mov r22,r21\n\tsubi r22,248\n\tcpi r22,16\n\tbrsh 9f\n\t" \
    "mov r23,r24\n\tmov r24,r25\n\tclr r25\n\t" \
    /* Recover the signed counter from the range test and set Z and N. */ \
    "subi r22,8\n\tbreq 19f\n\tbrmi 6f\n\t" \
    "18: add r23,r18\n\tadc r24,r19\n\tadc r25,__zero_reg__\n\t" \
    "dec r22\n\tbrne 18b\n\t19: rjmp 7f\n\t" \
    "6: sub r23,r18\n\tsbc r24,r19\n\tsbc r25,__zero_reg__\n\t" \
    "inc r22\n\tbrne 6b\n\trjmp 7f\n\t" \
    "9: mov r23,r21\n\tlsr r23\n\t" \
    ".rept 3\n\t" LPX4_NOMUL_LPC_PAIR ".endr\n\t" \
    LPX4_NOMUL_LPC_BIT \
    "brcc 3f\n\tsub r24,r18\n\tsbc r25,r19\n\t" \
    "3: ror r25\n\tror r24\n\tror r23\n\t" \
    "7: sbrs r19,7\n\trjmp 8f\n\tsub r24,r20\n\tsbc r25,r21\n\t8:\n\t"
#else
#define LPX4_NOMUL_PRODUCT \
    "tst r21\n\tbrne 9f\n\ttst r20\n\tbrne 7f\n\t" \
    "rjmp 5f\n\t7: rjmp 6f\n\t" \
    "9: cpi r21,255\n\tbrne 7f\n\tsbrc r20,7\n\trjmp 6f\n\t7:\n\t" \
    LPX4_NOMUL_SATURATED \
    "mov r22,r20\n\tclr r24\n\tclr r25\n\t" \
    ".rept 8\n\t" LPX4_NOMUL_HIGH_STEP ".endr\n\t" \
    "mov r22,r21\n\t" \
    ".rept 4\n\t" LPX4_NOMUL_HIGH_STEP ".endr\n\t" \
    ".rept 3\n\t" LPX4_NOMUL_HIGH_STEP "ror r23\n\t.endr\n\t" \
    "lsr r22\n\tbrcc 3f\n\tsub r24,r18\n\tsbc r25,r19\n\t" \
    "3: ror r25\n\tror r24\n\tror r23\n\t" \
    "sbrs r19,7\n\trjmp 4f\n\tsub r24,r20\n\tsbc r25,r21\n\t" \
    "4: rjmp 8f\n\t" \
    "6: mov r22,r20\n\tclr r23\n\tclr r24\n\tlsr r22\n\t" \
    ".rept 8\n\tbrcc 3f\n\tadd r23,r18\n\tadc r24,r19\n\t" \
    "3: ror r24\n\tror r23\n\tror r22\n\t.endr\n\t" \
    "sbrs r21,7\n\trjmp 4f\n\tsub r23,r18\n\tsbc r24,r19\n\t" \
    "4: sbrc r19,7\n\tsub r24,r20\n\t" \
    "mov r25,r24\n\tlsl r25\n\tsbc r25,r25\n\t8:\n\t"
#endif
#define LPX4_NOMUL_SUB \
    LPX4_NOMUL_PRODUCT \
    "andi r23,240\n\tsub %A0,r23\n\tsbc %B0,r24\n\tsbc %C0,r25\n\t" \
    "sbc %D0,__zero_reg__\n\tsbrc r25,7\n\tinc %D0\n\t5:\n\t"
#if LPX4_USE_AVR_NOMUL_ASM
// coefficient is below 16384; the endpoint is handled by AttenuateQ14.
// Bias the signed state by 32768, then subtract 2*coefficient after the
// Q14 shift. The bias contributes an integer, preserving the exact floor.
// One shared runtime-coefficient kernel serves both stream-defined filters.
static inline __attribute__((always_inline)) int16_t lpx4NomulAttenuate(uint16_t coefficient,int16_t state){
    uint16_t result,original=coefficient;
    __asm__(
        "subi %B3,128\n\t"
        "clr %A0\n\tclr %B0\n\t"
        // Seed the first round with zero or half of the biased state.
        "lsr %A1\n\tbrcc 4f\n\tmovw %A0,%A3\n\tlsr %B0\n\tror %A0\n\t4:\n\t"
        ".rept 7\n\tlsr %A1\n\tbrcc 2f\n\t"
        "add %A0,%A3\n\tadc %B0,%B3\n\t"
        "2: ror %B0\n\tror %A0\n\t.endr\n\t"
        ".rept 6\n\tlsr %B1\n\tbrcc 2f\n\t"
        "add %A0,%A3\n\tadc %B0,%B3\n\t"
        "2: ror %B0\n\tror %A0\n\t.endr\n\t"
        "lsl %A2\n\trol %B2\n\tsub %A0,%A2\n\tsbc %B0,%B2\n\t"
        : "=&r"(result),"+&r"(coefficient),"+&r"(original),"+&d"(state)
        : : "cc");
    return (int16_t)result;
}
#endif
// spareHistory explicitly requires h[11]; h[10] is a discarded shift slot.
// Default callers still require only h[10]. Q4 excitation is exactly integral.
// keepQ4 leaves the accumulated integer in Q4 units for a combined final clip.
// finalHistory exposes the history base from the completed reverse walk so the
// caller can store the clipped sample through the same address register.
// boundedLpc requires a[] in -32767..32767.
template<bool excitationQ4=false,bool spareHistory=false,bool keepQ4=false,bool boundedLpc=false>
static inline int32_t lpx4SynthesisQ12(int32_t excitation,const int16_t* a,int16_t* h,int16_t** finalHistory=nullptr){
#if LPX4_USE_AVR_ASM
    int32_t result=excitation;
    a+=10;h+=10;
    __asm__ (
        "clr r16\n\t"
        ".if %3\n\t.rept 4\n\tlsl %A0\n\trol %B0\n\trol %C0\n\trol %D0\n\t.endr\n\t.endif\n\t"
        LPX4_SYNTH_INIT
#if LPX4_COMPACT_VERSION==9 && LPX4_AVR_DOT_UNROLL==9
        // T distinguishes the two five-tap passes. Before pass one the oldest
        // word is only loaded. The tail prepares the next tap and shifts it
        // before pass two reuses the same five multiplies.
        ".if !%4 && !%3\n\t"
        "clt\n\t"
        LPX4_LPC_LOAD_REVERSE
        "1:\n\t"
        LPX4_SYNTH_MUL
        ".rept 4\n\t"
        LPX4_LPC_LOAD_REVERSE
        LPX4_LPC_SHIFT_HISTORY
        LPX4_SYNTH_MUL
        ".endr\n\tbrts 3f\n\tset\n\t"
        LPX4_LPC_LOAD_REVERSE
        LPX4_LPC_SHIFT_HISTORY
        "rjmp 1b\n\t3:\n\t"
        ".else\n\t"
#endif
        LPX4_LPC_LOAD_REVERSE
        ".if %4\n\t"
        LPX4_LPC_SHIFT_HISTORY
        ".endif\n\t"
        LPX4_SYNTH_MUL
#if LPX4_AVR_DOT_UNROLL!=9
        "ldi r17," LPX4_STRING(9/LPX4_AVR_DOT_UNROLL) "\n\t1:\n\t"
#endif
        ".rept " LPX4_STRING(LPX4_AVR_DOT_UNROLL) "\n\t"
        LPX4_LPC_LOAD_REVERSE
        LPX4_LPC_SHIFT_HISTORY
        LPX4_SYNTH_MUL
        ".endr\n\t"
#if LPX4_AVR_DOT_UNROLL!=9
        "dec r17\n\tbreq 2f\n\trjmp 1b\n\t2:\n\t"
#endif
#if LPX4_COMPACT_VERSION==9 && LPX4_AVR_DOT_UNROLL==9
        ".endif\n\t"
#endif
        ".if !%5\n\t.rept 4\n\tasr %D0\n\tror %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t.endif\n\t"
        "clr __zero_reg__\n\t"
        : "+&r" (result), "+z" (h), "+x" (a)
        : "I"(!excitationQ4),"I"(spareHistory),"I"(keepQ4)
        : "r0","r1","r16","r18","r19","r20","r21",
#if LPX4_AVR_DOT_UNROLL!=9
          "r17",
#endif
          LPX4_DOT_LOW_CLOBBER "r23","r24","r25","cc","memory"
    );
    if(finalHistory)*finalHistory=h;
    return result;
#elif LPX4_USE_AVR_NOMUL_ASM
    int32_t result=excitation;
#if LPX4_AVR25_SATURATED_PRODUCTS
    const uint8_t saturationHint=(uint8_t)(((uint16_t)h[0]>>8)-127)<2;
#endif
    a+=10;h+=10;
    __asm__(
#if LPX4_AVR25_SATURATED_PRODUCTS
        "bst %4,0\n\t"
#endif
        ".if %3\n\t.rept 4\n\tlsl %A0\n\trol %B0\n\trol %C0\n\trol %D0\n\t.endr\n\t.endif\n\t"
        "ldi r17,10\n\t1:\n\t"
        LPX4_LPC_LOAD_REVERSE
        ".if !%5\n\tcpi r17,10\n\tbreq 2f\n\t.endif\n\t"
        LPX4_LPC_SHIFT_HISTORY
        "2:\n\t"
        LPX4_NOMUL_SUB
        "dec r17\n\tbreq 2f\n\trjmp 1b\n\t2:\n\t"
        ".if !%6\n\t.rept 4\n\tasr %D0\n\tror %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t.endif\n\t"
        : "+&r"(result),"+z"(h),"+x"(a) : "I"(!excitationQ4)
#if LPX4_AVR25_SATURATED_PRODUCTS
          ,"r"(saturationHint)
#else
          ,"I"(0)
#endif
          ,"I"(spareHistory),"I"(keepQ4),"I"(boundedLpc)
        : "r17","r18","r19","r20","r21","r22","r23","r24","r25","cc","memory");
    if(finalHistory)*finalHistory=h;
    return result;
#else
    int32_t result=excitationQ4?(excitation+(excitation<0?15:0))>>4:excitation;
    for(int8_t i=9;i>=0;i--){
        result-=lpx4Shift12(lpx4Mul16(a[i],h[i]));
        if(spareHistory||i<9)h[i+1]=h[i];
    }
    if(finalHistory)*finalHistory=h;
    return keepQ4?result*16:result;
#endif
}
// Same exact sum, read-only mirrored history. h points just past ten old
// samples in reverse temporal order; return it advanced back by ten words.
// The caller then writes the new sample to h[0] and h[10]. Preconditions and
// Q4 bounds match SynthesisQ12; this helper never shifts/stores old samples.
template<bool excitationQ4=false>
static inline __attribute__((always_inline)) int32_t lpx4SynthesisRingQ12(int32_t excitation,const int16_t* a,int16_t*& h){
#if LPX4_USE_AVR_ASM
    int32_t result=excitation;
    __asm__ (
        "clr r16\n\t"
        ".if %3\n\t.rept 4\n\tlsl %A0\n\trol %B0\n\trol %C0\n\trol %D0\n\t.endr\n\t.endif\n\t"
        LPX4_SYNTH_INIT
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
        : "I"(!excitationQ4)
        : "r0","r1","r16","r18","r19","r20","r21",
#if LPX4_AVR_DOT_UNROLL!=9
          "r17",
#endif
          LPX4_DOT_LOW_CLOBBER "r23","r24","r25","cc","memory"
    );
    return result;
#else
    int32_t result=excitationQ4?excitation/16:excitation;
    for(uint8_t i=0;i<10;i++)result-=lpx4Shift12(lpx4Mul16(a[i],h[-1-i]));
    h-=10;
    return result;
#endif
}
#if LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9
// subframePosition points to the current position (0..19), with the ten
// history words at historyOffset bytes after it. Position modulo ten selects
// the oldest sample. Z reads the two spans in chronological order while X
// walks the coefficients backwards, then Z returns to the oldest slot.
#define LPX4_LPC_RING_TAP \
    "ld r19,-X\n\tld r18,-X\n\tld r20,Z+\n\tld r21,Z+\n\t" LPX4_SYNTH_MUL
template<uint8_t historyOffset>
static inline __attribute__((always_inline)) int16_t lpx4SynthesisCircularQ12(
        int32_t excitation,const int16_t* coefficients,uint8_t* subframePosition){
    int32_t result=excitation;
    const int16_t* a=coefficients+10;
    __asm__(
        "clr r16\n\t"
        LPX4_SYNTH_INIT
        "ld r22,Z\n\tadiw r30,%3\n\tcpi r22,10\n\tbrlo 7f\n\tsubi r22,10\n\t"
        "7: mov r17,r22\n\tlsl r17\n\tadd r30,r17\n\tadc r31,r16\n\t"
        "ldi r17,10\n\tsub r17,r22\n\tclt\n\t"
        // Enter on the second tap for odd spans. T marks the wrapped span
        // and the playback ISR preserves it with the rest of SREG.
        "lsr r17\n\tbrcs 2f\n\tdec r17\n\t"
        "1: " LPX4_LPC_RING_TAP
        "2: " LPX4_LPC_RING_TAP
        "subi r17,1\n\tbrcc 1b\n\t"
        "brts 4f\n\tsbiw r30,20\n\tset\n\tmov r17,r22\n\tlsr r17\n\t"
        "brcs 2b\n\tbreq 4f\n\tdec r17\n\trjmp 1b\n\t"
        // Bias the high word by eight. Values below 16 fit signed16 after
        // dropping the zero fractional nibble. Clip before writing history.
        "4: movw r24,%C0\n\tadiw r24,8\n\t"
        "cpi r24,16\n\tcpc r25,r16\n\tbrsh 5f\n\t"
        "swap %A0\n\tswap %B0\n\tmov r25,%B0\n\tandi r25,240\n\t"
        "or %A0,r25\n\teor %B0,r25\n\t"
        "swap r24\n\tsubi r24,128\n\tor %B0,r24\n\t"
        "ldi r25,128\n\tcp %B0,r25\n\tbrne 6f\n\t"
        "ldi r24,1\n\tcp %A0,r24\n\tadc %A0,r16\n\trjmp 6f\n\t"
        "5: ldi r24,255\n\tldi r25,127\n\tsbrs %D0,7\n\trjmp 7f\n\t"
        "ldi r24,1\n\tldi r25,128\n\t7: movw %A0,r24\n\t"
        "6: st Z+,%A0\n\tst Z,%B0\n\tclr __zero_reg__"
        : "+&r"(result),"+z"(subframePosition),"+x"(a)
        : "I"(historyOffset)
        : "r0","r1","r16","r17","r18","r19","r20","r21","r22","r23","r24","r25","cc","memory");
    return (int16_t)result;
}
#undef LPX4_LPC_RING_TAP
#endif

#undef LPX4_SYNTH_MUL
#undef LPX4_SYNTH_INIT
#undef LPX4_NOMUL_PRODUCT
#undef LPX4_NOMUL_SATURATED
#undef LPX4_NOMUL_HIGH_STEP
#undef LPX4_NOMUL_LPC_PAIR
#undef LPX4_NOMUL_LPC_BIT
#undef LPX4_NOMUL_SUB
#undef LPX4_DOT_PRODUCT
#undef LPX4_DOT_PRODUCT_BYTES
#undef LPX4_DOT_LOW_RESULT
#undef LPX4_DOT_LOW_CLOBBER
#undef LPX4_LPC_LOAD_REVERSE
#undef LPX4_LPC_SHIFT_HISTORY
#undef LPX4_DOT_MUL
#undef LPX4_STRING
#undef LPX4_STRING_

// Saturate a signed24 value to the synthesis range -32767..32767.
// Synthesis is bounded by +/-3145728. AVR inspects the low 24 bits;
// the C fallback takes a signed24 value sign-extended to int32_t.
template<bool compactAvr25=false>
static inline __attribute__((always_inline)) int16_t lpx4Clip15From24(int32_t value){
#if LPX4_USE_AVR_ASM || LPX4_USE_AVR_NOMUL_ASM
    int16_t result;
    __asm__(
        // EOR tests the sign byte without losing the carry needed to restore B.
        "lsl %B1\n\tsbc %A0,%A0\n\t"
        ".if %2\n\teor %A0,%C1\n\tbrne 1f\n\t.else\n\t"
        "cp %C1,%A0\n\tbrne 1f\n\tlsl %A0\n\t.endif\n\t"
        "ror %B1\n\tmovw %A0,%A1\n\t"
        // The exact signed16 minimum is excluded from the synthesis range.
        "cpi %B0,128\n\tbrne 2f\n\t.if %2\n\t"
        "cpi %A0,1\n\tadc %A0,__zero_reg__\n\t.else\n\t"
        "tst %A0\n\tbrne 2f\n\tinc %A0\n\t.endif\n\trjmp 2f\n\t"
        "1:\n\tldi %A0,255\n\tldi %B0,127\n\tsbrs %C1,7\n\trjmp 2f\n\t"
        "ldi %A0,1\n\tldi %B0,128\n\t2:\n\t"
        : "=&d"(result),"+r"(value) : "I"(compactAvr25 && LPX4_USE_AVR_NOMUL_ASM) : "cc");
    return result;
#else
    return value<-32767?-32767:(value>32767?32767:(int16_t)value);
#endif
}

// Synthesis has removed each term's fractional bits. Convert the integral
// Q4 accumulator and clip to -32767..32767 in one operation.
static inline __attribute__((always_inline)) int16_t lpx4ClipSynthesisQ4(int32_t value){
#if LPX4_USE_AVR_NOMUL_ASM
    uint8_t nibble;
    __asm__(
        // The two high bytes must represent -8..7 before narrowing.
        "subi %C0,248\n\tsbci %D0,255\n\t"
        "cpi %C0,16\n\tcpc %D0,__zero_reg__\n\tbrsh 1f\n\t"
        "swap %A0\n\tswap %B0\n\tmov %1,%B0\n\tandi %1,240\n\tor %A0,%1\n\t"
        "andi %B0,15\n\tswap %C0\n\tsubi %C0,128\n\tor %B0,%C0\n\t"
        "cpi %B0,128\n\tbrne 2f\n\tcpi %A0,1\n\tadc %A0,__zero_reg__\n\trjmp 2f\n\t"
        "1: ldi %A0,255\n\tldi %B0,127\n\tsbrs %D0,7\n\trjmp 2f\n\t"
        "ldi %A0,1\n\tldi %B0,128\n\t2:"
        : "+&d"(value),"=&d"(nibble) : : "cc");
    return (int16_t)value;
#else
    return lpx4Clip15From24(value/16);
#endif
}

// Halve a signed24 polynomial sum toward zero and clamp to the LPC range.
template<class Value>
static inline __attribute__((always_inline)) int16_t lpx4HalfClip15From24(Value value){
#if LPX4_USE_AVR_NOMUL_ASM || (LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9)
    // After biasing negative sums by one, only high bytes 0 and 255 can
    // fit after halving. INC maps them to 1 and 0, respectively. On the
    // narrow path CPI restores the sign to carry for the two-byte shift.
    __asm__(
        "sbrs %C0,7\n\trjmp 1f\n\t"
        "subi %A0,255\n\tsbci %B0,255\n\tsbci %C0,255\n\t"
        "1: inc %C0\n\tcpi %C0,2\n\tbrlo 3f\n\t"
        "ldi %A0,255\n\tldi %B0,127\n\tcpi %C0,129\n\tbrlo 2f\n\t"
        "ldi %A0,1\n\tldi %B0,128\n\trjmp 2f\n\t"
        "3: cpi %C0,1\n\tror %B0\n\tror %A0\n\t"
        "cpi %B0,128\n\tbrne 2f\n\tcpi %A0,1\n\tadc %A0,__zero_reg__\n\t2:"
        : "+d"(value) : : "cc");
    return (int16_t)value;
#else
    return lpx4Clip15From24(value/2);
#endif
}

// Full signed16 addition with the same non-minimum saturation range.
template<bool compactAvr25=false>
static inline __attribute__((always_inline)) int16_t lpx4AddClip15(int16_t a,int16_t b){
#if LPX4_USE_AVR_ASM || LPX4_USE_AVR_NOMUL_ASM
    __asm__(
        "add %A0,%A1\n\tadc %B0,%B1\n\tbrvc 1f\n\tbrmi 2f\n\t"
        // Negative overflow has a nonnegative wrapped sum; positive reverses it.
        "ldi %A0,1\n\tldi %B0,128\n\trjmp 3f\n\t"
        "2:\n\tldi %A0,255\n\tldi %B0,127\n\trjmp 3f\n\t"
        "1: cpi %B0,128\n\tbrne 3f\n\t.if %2\n\t"
        "cpi %A0,1\n\tadc %A0,__zero_reg__\n\t.else\n\t"
        "tst %A0\n\tbrne 3f\n\tinc %A0\n\t.endif\n\t3:"
        : "+&d"(a) : "r"(b),"I"(compactAvr25 && LPX4_USE_AVR_NOMUL_ASM) : "cc");
    return a;
#else
    const int32_t sum=(int32_t)a+b;
    return sum<-32767?-32767:(sum>32767?32767:(int16_t)sum);
#endif
}

static inline __attribute__((always_inline)) int16_t lpx4ClipQ14(int16_t value){
#if LPX4_USE_AVR_NOMUL_ASM && LPX4_AVR25_SATURATED_PRODUCTS
    uint8_t high;
    __asm__(
        "mov %1,%B0\n\tsubi %1,192\n\tbrpl 1f\n\t"
        "clr %A0\n\tldi %B0,64\n\tsbrc %1,6\n\tori %B0,128\n\t1:\n\t"
        : "+&d"(value),"=&d"(high) : : "cc");
    return value;
#else
    return value<-16384?-16384:(value>16384?16384:value);
#endif
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
        // Add both the rounding bias32 and PWM offset128*64 before extraction.
        // The unsigned wrapped word is valid iff <16384; every other value
        // clips according to the original sample sign (gain is unsigned).
        "subi %A1,224\n\tsbci %B1,223\n\t"
        "cpi %B1,64\n\tbrlo 1f\n\t"
        "ldi %0,255\n\tsbrc %B2,7\n\tclr %0\n\trjmp 2f\n\t"
        "1:\n\t.rept 2\n\tlsl %A1\n\trol %B1\n\t.endr\n\t"
        "mov %0,%B1\n\t2:\n\t"
        "clr __zero_reg__\n\t"
        : "=&d"(result),"=&a"(high) : "a"(sample),"a"(gain) : "r0","r1","cc");
    return result;
#elif LPX4_USE_AVR_NOMUL_ASM
    if(gain==130){
        // Write sample=128*k+r, 0<=r<128. Equivalently extract the rounded
        // product65/8192 after adding the unsigned PWM offset. Only 24 bits
        // suffice. Form sample<<6 as (sample<<8)>>2, exactly in signed24;
        // all signed16 inputs retain clipping.
        int32_t product=sample;
        const int8_t sign=sample<0?-1:0;
        uint8_t result;
        __asm__(
            "mov %C1,%B1\n\tmov %B1,%A1\n\tclr %A1\n\t"
            ".rept 2\n\tasr %C1\n\tror %B1\n\tror %A1\n\t.endr\n\t"
            "add %A1,%A2\n\tadc %B1,%B2\n\tadc %C1,%3\n\t"
            "subi %B1,240\n\tsbci %C1,239\n\t"
            "cpi %C1,32\n\tbrlo 1f\n\tldi %0,255\n\t"
            "sbrc %B2,7\n\tclr %0\n\trjmp 2f\n\t"
            "1: .rept 3\n\tlsl %B1\n\trol %C1\n\t.endr\n\t"
            "mov %0,%C1\n\t2:\n\t"
            : "=&d"(result),"+&d"(product) : "r"(sample),"r"(sign) : "cc");
        return result;
    }
    const int32_t duty=128+lpx4Shift14(lpx4ByteWord<false,true>(gain,(uint16_t)sample)+8192);
    return duty<0?0:(duty>255?255:(uint8_t)duty);
#else
    const uint32_t biased=(uint32_t)((int32_t)sample*gain+2105344L);
    if(biased>=4194304UL)return sample<0?0:255;
    const uint16_t window=(uint16_t)(biased>>8);
    return (uint8_t)(window>>6);
#endif
}

// For |sample| <= 27853, gain 130 gives the rounded duty
// floor((sample+floor(sample/64)+16448)/128) before saturation.
// The numerator lies in [-11841,44736]. Bit 15 of its wrapped value
// signals either rail, and bit 14 distinguishes the lower rail.
static inline __attribute__((always_inline)) uint8_t lpx4PwmBounded130(int16_t sample){
#if LPX4_USE_AVR_ASM || LPX4_USE_AVR_NOMUL_ASM
    uint16_t total=(uint16_t)sample,shifted;
    uint8_t sign;
    __asm__(
        "movw %A1,%A0\n\t"
        "lsl %A1\n\trol %B1\n\tsbc %2,%2\n\t"
        "lsl %A1\n\trol %B1\n\trol %2\n\t"
        "add %A0,%B1\n\tadc %B0,%2\n\t"
        "subi %A0,192\n\tsbci %B0,191\n\t"
        "lsl %A0\n\trol %B0\n\tbrcc 1f\n\t"
        "cpi %B0,128\n\tsbc %B0,%B0\n\t1:"
        : "+&d"(total),"=&w"(shifted),"=&r"(sign) : : "cc");
    return (uint8_t)(total>>8);
#else
    return lpx4PwmQ14(sample,130);
#endif
}

// Bounded attenuation: coefficient 0..16384, signed16 state, exact floor Q14.
// The result fits signed16. Keep the generic full-range MulQ14 below.
static inline int16_t lpx4AttenuateQ14(uint16_t coefficient,int16_t state){
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
#elif LPX4_USE_AVR_NOMUL_ASM
    // Only the unity endpoint has bit 14 set in the bounded domain.
    if(coefficient&16384)return state;
    if((uint8_t)coefficient==0 && (uint8_t)(coefficient>>8)==32)return state>>1;
    if(coefficient==64)return state>>8;
    return lpx4NomulAttenuate(coefficient,state);
#else
    const uint32_t product=(uint32_t)((int32_t)coefficient*state);
    return (int16_t)((product<<2)>>16);
#endif
}

#if LPX4_USE_AVR_NOMUL_ASM
// Tag the two shift-only coefficients after validating the stream header.
// The common offset keeps unity at 0x4000 and puts 64 at 0xa040 and
// 8192 at 0xc000. The tags are only used by the prepared AVR25 kernel.
static __attribute__((noinline)) uint16_t lpx4PrepareAttenuationQ14(uint16_t coefficient){
    if(coefficient==8192 || coefficient==64)coefficient+=0xa000u;
    return coefficient;
}

// GNU AVR ABI: state arrives and returns in r25:r24. The coefficient
// arrives in r23:r22. The leaf uses only call-clobbered registers and flags.
static __attribute__((naked,noinline,noclone)) int16_t lpx4PreparedAttenuationQ14(int16_t,uint16_t){
    __asm__ volatile(
        "cpi r23,64\n\tbrsh 7f\n\t"
        // Bias the signed state by 32768 and save the unshifted coefficient.
        "movw r18,r24\n\tmovw r20,r22\n\tsubi r19,128\n\tclr r24\n\tclr r25\n\t"
        "lsr r22\n\tbrcc 4f\n\tmovw r24,r18\n\tlsr r25\n\tror r24\n\t4:\n\t"
        "lsr r22\n\tbrcc 2f\n\tadd r24,r18\n\tadc r25,r19\n\t"
        "2: ror r25\n\tror r24\n\t"
        // The six remaining low-byte rounds and six high-byte rounds share code.
        "clt\n\t5:\n\t.rept 6\n\t"
        "lsr r22\n\tbrcc 2f\n\tadd r24,r18\n\tadc r25,r19\n\t"
        "2: ror r25\n\tror r24\n\t.endr\n\tbrts 6f\n\tset\n\tmov r22,r23\n\trjmp 5b\n\t"
        // Undo the bias by subtracting exactly twice the coefficient.
        "6: lsl r20\n\trol r21\n\tsub r24,r20\n\tsbc r25,r21\n\tret\n\t"
        // CPI leaves Z for unity and N distinguishes the two shift tags.
        "7: brne 8f\n\tret\n\t8: brpl 10f\n\t"
        "asr r25\n\tror r24\n\tret\n\t"
        "10: mov r24,r25\n\tlsl r25\n\tsbc r25,r25\n\tret");
}
#endif

// A ROM player may pin validated stream-wide filter constants at build time.
// The public/default decoder retains dynamic parameters and portable arithmetic.
template<uint16_t coefficient>
static inline __attribute__((always_inline)) int16_t lpx4AttenuateFixedQ14(int16_t state){
    static_assert(coefficient<=16384,"Invalid fixed attenuation");
    if(coefficient==0)return 0;
    if(coefficient==8192)return state>>1;
    if(coefficient==64)return state>>8;
    if(coefficient==16384)return state;
#if LPX4_USE_AVR_NOMUL_ASM
    // A[j+1]=floor((A[j]+bit[j]*uint16(state))/2). After14 bits A is
    // floor(coefficient*uint16(state)/16384); no low product bytes are needed.
    // Correct a negative state by exactly4*coefficient in the result word.
    uint16_t result;
    __asm__(
        "clr %A0\n\tclr %B0\n\t"
        ".irp bit,0,1,2,3,4,5,6,7,8,9,10,11,12,13\n\t"
        ".if (%2 & (1<<\\bit))\n\tadd %A0,%A1\n\tadc %B0,%B1\n\t.else\n\tclc\n\t.endif\n\t"
        "ror %B0\n\tror %A0\n\t.endr\n\t"
        "sbrs %B1,7\n\trjmp 1f\n\tsubi %A0,lo8(4*%2)\n\tsbci %B0,hi8(4*%2)\n\t1:\n\t"
        : "=&d"(result) : "r"(state),"n"(coefficient) : "cc");
    return (int16_t)result;
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
#elif LPX4_USE_AVR_NOMUL_ASM
    return ((int32_t)x*y)>>14;
#else
    return lpx4Shift14((int32_t)x*y);
#endif
}
