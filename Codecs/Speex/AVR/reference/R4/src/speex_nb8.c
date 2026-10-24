/* Restricted Speex NB 8kbps decoder, experimental AVR-specific rewrite.
 * Fixed-point mode-3 reconstruction, no encoder/VBR/PLC/highpass/enhancer.
 * Algorithms and codebooks derived from BSD-3-Clause Xiph Speex 1.2.1.
 */
#include "speex_nb8.h"
#include <string.h>
#ifdef __AVR__
#include <avr/pgmspace.h>
#define FLASH PROGMEM
#define R8(p) ((int8_t)pgm_read_byte(p))
#define R16(p) ((int16_t)pgm_read_word(p))
#define R32(p) ((int32_t)pgm_read_dword(p))
#else
#define FLASH
#define R8(p) (*(p))
#define R16(p) (*(p))
#define R32(p) (*(p))
#endif


/* Signed 16 x 16 -> signed 32-bit product.
 * AVR201 algorithm with operands constrained to r16..r23 (`a`) for MULSU.
 * __zero_reg__ (r1) is explicitly restored to zero for the AVR C ABI.
 * The early-clobber output registers must not alias either input pair.
 * On non-AVR hosts use ordinary multiplication for bit-identity testing.
 */
static inline int32_t avr_mul_s16_s16(int16_t lhs, int16_t rhs) {
#ifdef __AVR__
    uint16_t lo, hi;
    /* Four hardware 8-bit multiplications, signed high-byte corrections. */
    __asm__ volatile (
        "clr r2\n\t"
        "muls %B2, %B3\n\t"
        "movw %A1, r0\n\t"
        "mul %A2, %A3\n\t"
        "movw %A0, r0\n\t"
        "mulsu %B2, %A3\n\t"
        "sbc %B1, r2\n\t"
        "add %B0, r0\n\t"
        "adc %A1, r1\n\t"
        "adc %B1, r2\n\t"
        "mulsu %B3, %A2\n\t"
        "sbc %B1, r2\n\t"
        "add %B0, r0\n\t"
        "adc %A1, r1\n\t"
        "adc %B1, r2\n\t"
        "clr __zero_reg__\n\t"
        : "=&r" (lo), "=&r" (hi)
        : "a" (lhs), "a" (rhs)
        : "r0", "r1", "r2", "cc"
    );
    return (int32_t)(((uint32_t)hi << 16) | lo);
#else
    return (int32_t)lhs * (int32_t)rhs;
#endif
}

extern const int8_t cdbk_nb[640];
extern const int8_t cdbk_nb_low1[320];
extern const int8_t cdbk_nb_high1[320];
extern const int8_t gain_cdbk_lbr[128];
extern const int8_t exc_10_32_table[320];

static const int32_t ol_gain_table[32] FLASH = {
    18900,25150,33468,44536,59265,78865,104946,139653,
    185838,247297,329081,437913,582736,775454,1031906,1373169,
    1827293,2431601,3235761,4305867,5729870,7624808,10146425,13501971,
    17967238,23909222,31816294,42338330,56340132,74972501,99766822,132760927
};
static const int16_t fine_gain_table[2] FLASH={11546,17224};

/* A 0..pi lookup table is generated offline. 2*cos(angle) in Q14. */
extern const int16_t cos2_q14_table[203];

/* Reconstruct one 160-bit Speex packet: MSB-first and tightly bit-packed. */
typedef struct { const uint8_t *bytes; uint8_t bit; } BitReader;
static __attribute__((noinline)) uint16_t take_bits(BitReader *br, uint8_t n) {
    /* Every mode-3 field is <= 7 bits. A field spans no more than
     * two bytes, so avoid advancing a bit at a time (160 loop trips).
     */
    uint8_t pos=br->bit;
    uint8_t offset=(uint8_t)(pos&7);
    uint8_t byte=(uint8_t)(br->bytes[pos>>3]<<offset);
    if ((uint8_t)(offset+n)>8)
        byte |= (uint8_t)(br->bytes[(pos>>3)+1]>>(8-offset));
    br->bit=(uint8_t)(pos+n);
    return (uint8_t)(byte>>(8-n));
}
static int16_t sat16(int32_t x) {
    if (x>32767) return 32767;
    if (x<-32767) return -32767;
    return (int16_t)x;
}
static int32_t mul16_32_q14(int16_t a, int32_t b) {
    /* Restricted Speex mode 3: b is bounded here:
       - gain: table[31] <= 132760927; later scaled <= ~115M
       - polynomial: each factor has |coefficients| <= [1, 2, 1],
         so each coefficient after five stages is bounded by the
         corresponding binomial C(10,k)*2^20 plus tiny roundoff;
         max C(10,k)=252, hence |b| < 2^29.
       Thus b>>14 always fits signed int16, without a dynamic fallback.
       Not a general-purpose 16x32 routine! */
    return avr_mul_s16_s16(a,(int16_t)(b>>14)) +
           (avr_mul_s16_s16(a,(int16_t)(b&16383))>>14);
}
static int32_t mul16_32_q15(int16_t a, int32_t b) {
    /* Only used with fixed positive ol_gain_table up to 132760927. */
    return avr_mul_s16_s16(a,(int16_t)(b>>15)) +
           (avr_mul_s16_s16(a,(int16_t)(b&32767))>>15);
}
static int16_t cos2_q14(uint16_t angle) {
    /* LSP angle stored in Q13; 25736 approximately pi. */
    if (angle>25736) angle=25736;
    uint8_t idx=(uint8_t)(angle>>7);
    uint8_t frac=(uint8_t)(angle&127);
    int16_t a=R16(&cos2_q14_table[idx]);
    int16_t b=R16(&cos2_q14_table[(uint8_t)(idx+1)]);
    return (int16_t)(a+((avr_mul_s16_s16((int16_t)(b-a), (int16_t)frac)+64)>>7));
}
static uint8_t lsp_dequant_checked(const SpeexNB8 *state,int16_t lsp[10], uint8_t i0, uint8_t i1, uint8_t i2) {
    uint16_t changed=0;
    for(uint8_t i=0;i<10;i++) {
        int16_t a=(int16_t)(i+1)*2048 + (int16_t)R8(&cdbk_nb[(uint16_t)i0*10+i])*32;
        int8_t delta = i<5 ? R8(&cdbk_nb_low1[(uint16_t)i1*5+i]) : R8(&cdbk_nb_high1[(uint16_t)i2*5+i-5]);
        lsp[i]=(int16_t)(a+(int16_t)delta*16);
        changed |= (uint16_t)(lsp[i] ^ state->old_lsp[i]);
    }
    return state->started && (changed==0);
}
static void lsp_interpolate(const SpeexNB8 *s,const int16_t new_lsp[10],int16_t out[10],uint8_t sub) {
    /* The original Q14 interpolation weights are exact multiples of 1/4.
     * Keeping two independent rounded terms ensures PCM bit identity. */
    for(uint8_t i=0;i<10;i++) {
        int16_t old=s->old_lsp[i], n=new_lsp[i];
        if(sub==0) out[i]=(int16_t)((avr_mul_s16_s16(old,3)+2)>>2)+ (int16_t)((n+2)>>2);
        else if(sub==1) out[i]=(int16_t)((old+1)>>1)+ (int16_t)((n+1)>>1);
        else if(sub==2) out[i]=(int16_t)((old+2)>>2)+ (int16_t)((avr_mul_s16_s16(n,3)+2)>>2);
        else out[i]=n;
    }
    if(out[0]<16) out[0]=16;
    if(out[9]>25720) out[9]=25720;
    for(uint8_t i=1;i<9;i++) {
        if(out[i] < out[i-1]+16) out[i]=(int16_t)(out[i-1]+16);
        if(out[i] > out[i+1]-16) out[i]=(int16_t)((out[i]>>1)+((out[i+1]-16)>>1));
    }
}
static void lsp_to_lpc_small(const int16_t lsp[10],int16_t lpc[10]) {
    /* The product of palindromic [1,-2cos(w),1] sections is palindromic.
     * Only update the first half, then mirror the rest exactly. This cuts
     * the number of expensive Q14 multiplications from 60 to 30. */
    int32_t p[11]={1048576};
    int32_t q[11]={1048576};
    for(uint8_t stage=0;stage<5;stage++) {
        int16_t cp=(int16_t)-cos2_q14((uint16_t)lsp[stage*2]);
        int16_t cq=(int16_t)-cos2_q14((uint16_t)lsp[stage*2+1]);
        uint8_t m=(uint8_t)(stage+1);
        for(int8_t j=(int8_t)m;j>=1;j--) {
            int32_t pp= j>=2 ? p[(uint8_t)(j-2)] : 0;
            int32_t qq= j>=2 ? q[(uint8_t)(j-2)] : 0;
            p[(uint8_t)j] += mul16_32_q14(cp,p[(uint8_t)(j-1)])+pp;
            q[(uint8_t)j] += mul16_32_q14(cq,q[(uint8_t)(j-1)])+qq;
        }
        for(uint8_t j=0;j<m;j++) {
            p[(uint8_t)(2*m-j)]=p[j];
            q[(uint8_t)(2*m-j)]=q[j];
        }
    }
    for(uint8_t j=1;j<=10;j++) {
        int32_t a=p[j]+p[j-1]+q[j]-q[j-1];
        lpc[j-1]=sat16((a+128)>>8);
    }
}
static int16_t excitation_get(const SpeexNB8 *s, uint16_t absolute) {
    return s->history[(uint8_t)absolute];
}
static void excitation_set(SpeexNB8 *s, uint16_t absolute, int16_t v) {
    s->history[(uint8_t)absolute]=v;
}
static void generate_pitch_innovation(SpeexNB8 *s,uint16_t base,uint8_t pitch_index,uint8_t gain_index,
                                      uint8_t correction,const uint8_t idx[4],int32_t ol_gain) {
    uint8_t pitch=(uint8_t)(17u+pitch_index);
    uint8_t base8=(uint8_t)base;
    int16_t gain[3];
    for(uint8_t i=0;i<3;i++) gain[2-i]=(int16_t)((32+R8(&gain_cdbk_lbr[(uint16_t)gain_index*4+i]))*128);
    uint8_t pitch_offset[3] = {(uint8_t)(pitch+1),pitch,(uint8_t)(pitch-1)};
    int32_t ener=mul16_32_q14(R16(&fine_gain_table[correction]),ol_gain);
    uint8_t subvec=0, subpos=0;
    for(uint8_t j=0;j<40;j++) {
        int32_t pitch32=0;
        for(uint8_t i=0;i<3;i++) {
            uint8_t pp=pitch_offset[i];
            uint8_t back;
            if(j<pp) back=(uint8_t)(base8+j-pp);
            else if(j<(uint16_t)pp+pitch) back=(uint8_t)(base8+j-pp-pitch);
            else continue;
            pitch32+=avr_mul_s16_s16(gain[i],excitation_get(s,back));
        }
        if(pitch32>262144000L) pitch32=262144000L;
        if(pitch32<-262144000L) pitch32=-262144000L;
        /* innovation raw shape is <<(14-5) = <<9 in Speex Q14. */
        int8_t shape=R8(&exc_10_32_table[(uint16_t)idx[subvec]*10+subpos]);
        int32_t innov=mul16_32_q14((int16_t)shape*4, ener);
        /* Final excitation: (2*pitch32 + innov*128) >> 14; splitting
         * prevents 32-bit overflow without emulated 64-bit multiply. */
        int32_t e=((pitch32+4096)>>13) + ((innov+64)>>7);
        excitation_set(s,(uint16_t)(base+j),sat16(e));
        if (++subpos == 10) { subpos=0; ++subvec; }
    }
}
static int16_t lpc_sample(SpeexNB8 *s, int16_t x) {
    /* Speex 10-pole iir_mem16, using coefficients from preceding subframe */
    /* Explicit modular addition avoids signed-overflow UB for malformed streams. */
    int32_t rounded=(int32_t)((uint32_t)s->synth_mem[0]+UINT32_C(4096));
    int16_t y=sat16((int32_t)x + (rounded>>13));
    int16_t neg=(int16_t)-y;
#if defined(__AVR__) && !defined(NB8_NO_LPC_ASM)
    extern void speex_nb8_lpc_update_asm(int32_t *mem, const int16_t *coef, int16_t neg_y);
    speex_nb8_lpc_update_asm(s->synth_mem,s->previous_lpc,neg);
#else
    for(uint8_t j=0;j<9;j++) s->synth_mem[j]=(int32_t)((uint32_t)s->synth_mem[j+1]+(uint32_t)avr_mul_s16_s16(s->previous_lpc[j],neg));
    s->synth_mem[9]=avr_mul_s16_s16(s->previous_lpc[9],neg);
#endif
    return y;
}
void speex_nb8_init(SpeexNB8 *state) {
    memset(state,0,sizeof(*state));
}
int speex_nb8_decode(SpeexNB8 *s, const uint8_t input[NB8_BYTES],int16_t pcm[NB8_SAMPLES]) {
    BitReader br={input,0};
    if(take_bits(&br,1)!=0||take_bits(&br,4)!=3) return -1;
    uint8_t idx0=(uint8_t)take_bits(&br,6);
    uint8_t idx1=(uint8_t)take_bits(&br,6);
    uint8_t idx2=(uint8_t)take_bits(&br,6);
    uint8_t qe=(uint8_t)take_bits(&br,5);
    int32_t ol_gain=mul16_32_q15(28406,R32(&ol_gain_table[qe]));
    int16_t new_lsp[10];
    uint8_t reuse=lsp_dequant_checked(s,new_lsp,idx0,idx1,idx2);
    if(!s->started) memcpy(s->old_lsp,new_lsp,sizeof(new_lsp));
    uint16_t base=s->sample_index;
    for(uint8_t sf=0;sf<4;sf++) {
        uint8_t pitch=(uint8_t)take_bits(&br,7);
        uint8_t gain=(uint8_t)take_bits(&br,5);
        uint8_t correction=(uint8_t)take_bits(&br,1);
        uint8_t idx[4];
        for(uint8_t i=0;i<4;i++) idx[i]=(uint8_t)take_bits(&br,5);
        generate_pitch_innovation(s,(uint16_t)(base+(uint16_t)sf*40),pitch,gain,correction,idx,ol_gain);
    }
    for(uint8_t sf=0;sf<4;sf++) {
        int16_t interp[10];
        int16_t next_lpc[10];
        if(!reuse) {
            lsp_interpolate(s,new_lsp,interp,sf);
            lsp_to_lpc_small(interp,next_lpc);
        }
        for(uint8_t j=0;j<40;j++) {
            uint16_t pos=(uint16_t)(base+(uint16_t)sf*40u+j-40u);
            pcm[(uint16_t)sf*40u+j]=lpc_sample(s,excitation_get(s,pos));
        }
        if(!reuse) memcpy(s->previous_lpc,next_lpc,sizeof(next_lpc));
    }
    memcpy(s->old_lsp,new_lsp,sizeof(new_lsp));
    s->sample_index=(uint16_t)(base+160u);
    s->started=1;
    return br.bit==160?0:-2;
}
