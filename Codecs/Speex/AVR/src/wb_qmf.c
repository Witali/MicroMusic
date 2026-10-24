#include "wb_qmf.h"
#include "avr_tables.h"
/* Center 16 coefficients of Xiph's h0, normalized to unity DC, rounded Q7.
 * Each phase's absolute coefficient sum is 236. With |half input|<=32768,
 * the accumulator including rounding is strictly inside signed24. */
static const int8_t h[16] AVR_TABLE={-4,-10,7,15,-14,-26,37,123,123,37,-26,-14,15,7,-10,-4};
static void save16(uint8_t *p,int32_t v)
{p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static int32_t read16(const uint8_t *p)
{return (int16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8));}
static int16_t finish(uint32_t v)
{int32_t s=(int32_t)(v+32)>>6;return s>32767?32767:s< -32767?-32767:(int16_t)s;}
SPEEX_NB3_HOT void speex_wb_qmf40_c(const int16_t *low,const int16_t *high,int16_t *out,uint8_t *state)
{
    unsigned i,k,pos=0;
    for(i=0;i<40;i++) {
        uint32_t even=0,odd=0;
        save16(state+pos,((int32_t)low[i]-high[i])>>1);
        save16(state+pos+2,((int32_t)low[i]+high[i])>>1);
        for(k=0;k<4;k++) state[pos+32+k]=state[pos+k];
        for(k=0;k<8;k++) {
            const uint8_t *p=state+pos+32-4*k;
            even+=(uint32_t)((int32_t)AVR_READ_I8(h+2*k)*read16(p));
            odd+=(uint32_t)((int32_t)AVR_READ_I8(h+2*k+1)*read16(p+2));
        }
        out[2*i]=finish(even);out[2*i+1]=finish(odd);
        pos+=4;if(pos==32)pos=0;
    }
}
