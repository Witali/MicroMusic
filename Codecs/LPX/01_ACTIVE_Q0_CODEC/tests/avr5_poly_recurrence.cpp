#include <avr/interrupt.h>
#include "Lpx4HybridCore.cpp"

extern "C" {
volatile uint32_t math_cases, math_irqs;
volatile uint8_t math_done, math_error, math_zero_error;
volatile uint8_t math_backend=LPX4_USE_AVR_ASM;
}

ISR(TIMER1_OVF_vect) {
    ++math_irqs;
}

static int8_t work[256] __attribute__((section(".bss"),aligned(256),used));
static uint16_t randomState=23;

static int16_t cosine(uint8_t trial,uint8_t phase) {
    if (trial==0) return -8192;
    if (trial==1) return 8192;
    if (trial==2) return phase&1 ? -8192 : 8192;
    if (trial==3) return phase&1 ? 8192 : -8192;
    randomState=randomState*421U+19U;
    return (int16_t)(randomState&16383)-8192;
}

static int32_t referenceProduct(int32_t coefficient,int16_t factor) {
    if(coefficient>=-250000 && coefficient<=250000) return (coefficient*factor)>>12;
    return (((coefficient/16)*factor)>>8)+(((coefficient%16)*factor)>>12);
}

static void referenceFactor(int32_t* polynomial,uint8_t degree,int16_t factor) {
    for (int8_t j=degree+2;j>=1;--j) {
        const int32_t own=j<=degree?polynomial[j]:0;
        const int32_t middle=j<=degree+1?referenceProduct(polynomial[j-1],factor):0;
        const int32_t earlier=j>=2?polynomial[j-2]:0;
        polynomial[j]=own+middle+earlier;
    }
}

int main() {
    math_backend=LPX4_USE_AVR_ASM;
    TIMSK1=_BV(TOIE1);
    TCCR1B=_BV(CS10);
    sei();
    for (uint16_t position=0;position<256 && !math_error;++position) {
        const uint8_t pbase=(uint8_t)((position+3)&252),qbase=pbase+24;
        for (uint8_t trial=0;trial<64 && !math_error;++trial) {
            int32_t p[12]={4096,4096},q[12]={4096,-4096};
            for (uint16_t i=0;i<256;++i) work[i]=(int8_t)0xa5;
            ringPolyStore24(work,pbase,4096);
            ringPolyStore24(work,qbase,4096);
            for (uint8_t stage=0;stage<5 && !math_error;++stage) {
                const uint8_t n=2*stage+2;
                for (uint8_t odd=0;odd<2 && !math_error;++odd) {
                    const int16_t c=cosine(trial,(uint8_t)(stage+odd));
                    const uint8_t base=odd?qbase:pbase;
                    int32_t* reference=odd?q:p;
                    ringPolyFactor(work,base,c,n,!odd);
                    uint8_t zero;
                    __asm__ volatile("mov %0,__zero_reg__" : "=r"(zero));
                    if(zero) math_zero_error=1;
                    referenceFactor(reference,n-1,c);
                    const uint8_t end=odd?n:n/2;
                    for (uint8_t i=0;i<=end;++i)
                        if (ringPolyLoad24(work,base+4*i)!=reference[i]) math_error=1;
                    ++math_cases;
                }
                for (uint16_t i=0;i<256;++i) {
                    const uint8_t relative=(uint8_t)(i-pbase);
                    if ((relative>=68 || (relative&3)==3) && work[i]!=(int8_t)0xa5) math_error=2;
                }
            }
        }
    }
    math_done=1;
    for (;;) {}
}
