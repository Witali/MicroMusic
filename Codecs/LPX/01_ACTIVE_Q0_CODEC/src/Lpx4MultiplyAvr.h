// Private multiplication backend, selected only by Lpx4Math.h.
#pragma once

// Real AVR ISA and explicit ASM enable are checked by Lpx4Math.h.
#if LPX4_USE_AVR_NOMUL_ASM
template<bool signedByte,bool signedWord>
static inline __attribute__((always_inline)) int32_t lpx4ByteWord(uint8_t x,uint16_t y){
    int32_t result;
    __asm__(
        "mov %A0,%1\n\tclr %B0\n\tclr %C0\n\tlsr %A0\n\t"
        ".rept 8\n\tbrcc 1f\n\tadd %B0,%A2\n\tadc %C0,%B2\n\t"
        "1: ror %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        ".if %3\n\tsbrs %1,7\n\trjmp 2f\n\tsub %B0,%A2\n\tsbc %C0,%B2\n\t2:\n\t.endif\n\t"
        ".if %4\n\tsbrc %B2,7\n\tsub %C0,%1\n\t.endif\n\t"
        "mov %D0,%C0\n\tlsl %D0\n\tsbc %D0,%D0\n\t"
        : "=&r"(result) : "r"(x),"r"(y),"I"(signedByte),"I"(signedWord) : "cc");
    return result;
}
#endif


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
    return lpx4ByteWord<true,true>((uint8_t)x,(uint16_t)y);
#endif
}

static inline __attribute__((always_inline)) int32_t lpx4Mul8xU16(int8_t x,uint16_t y){
#if LPX4_USE_AVR_ASM
    int32_t result;
    __asm__(
        "mulsu %1,%A2\n\tmovw %A0,r0\n\t"
        "mov %C0,r1\n\tlsl %C0\n\tsbc %C0,%C0\n\t"
        "mulsu %1,%B2\n\tadd %B0,r0\n\tadc %C0,r1\n\t"
        "mov %D0,%C0\n\tlsl %D0\n\tsbc %D0,%D0\n\tclr __zero_reg__\n\t"
        : "=&r"(result) : "a"(x),"a"(y) : "r0","r1","cc");
    return result;
#else
    if(!x)return 0;
    if(x==1)return y;
    if(x==-1)return -(int32_t)y;
    if(x==3 || x==-3){
        uint32_t triple=y;
        __asm__("lsl %A0\n\trol %B0\n\trol %C0\n\t"
                "add %A0,%A1\n\tadc %B0,%B1\n\tadc %C0,__zero_reg__\n\t"
                : "+&r"(triple) : "r"(y) : "cc");
        return x<0?-(int32_t)triple:(int32_t)triple;
    }
    return lpx4ByteWord<true,false>((uint8_t)x,y);
#endif
}

static LPX4_MUL_INLINE int32_t lpx4Mul16(int16_t x,int16_t y){
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
    // Original AVR25 prototype: unsigned carry-rotation product, followed by
    // two independent modulo-2^32 signed corrections. Includes signed minima.
    uint32_t result;
    uint16_t original=y;
#if LPX4_AVR25_MUL16_UNROLL == 16
    __asm__(
        "movw %A0,%A2\n\tclr %C0\n\tclr %D0\n\t"
        "lsr %B0\n\tror %A0\n\t"
        ".rept 16\n\tbrcc 1f\n\tadd %C0,%A1\n\tadc %D0,%B1\n\t"
        "1: ror %D0\n\tror %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        "sbrs %B1,7\n\trjmp 2f\n\tsub %C0,%A2\n\tsbc %D0,%B2\n\t"
        "2: sbrs %B2,7\n\trjmp 3f\n\tsub %C0,%A1\n\tsbc %D0,%B1\n\t3:\n\t"
        : "=&r"(result) : "r"(x),"r"(original) : "cc");
#else
    uint8_t groups;
    __asm__(
        "movw %A0,%A3\n\tclr %C0\n\tclr %D0\n\t"
        "lsr %B0\n\tror %A0\n\tldi %1,%5\n\t0:\n\t"
        ".rept %4\n\tbrcc 1f\n\tadd %C0,%A2\n\tadc %D0,%B2\n\t"
        "1: ror %D0\n\tror %C0\n\tror %B0\n\tror %A0\n\t.endr\n\t"
        // DEC and BRNE leave C intact: the last ROR supplies the next bit.
        "dec %1\n\tbrne 0b\n\t"
        "sbrs %B2,7\n\trjmp 2f\n\tsub %C0,%A3\n\tsbc %D0,%B3\n\t"
        "2: sbrs %B3,7\n\trjmp 3f\n\tsub %C0,%A2\n\tsbc %D0,%B2\n\t3:\n\t"
        : "=&r"(result),"=&d"(groups) : "r"(x),"r"(original),
          "I"(LPX4_AVR25_MUL16_UNROLL),"I"(16/LPX4_AVR25_MUL16_UNROLL) : "cc");
#endif
    return (int32_t)result;
#endif
}
