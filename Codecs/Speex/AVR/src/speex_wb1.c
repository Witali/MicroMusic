/* Restricted NB3 + HB1 folding from Xiph Speex 1.2.1 sb_celp.c.
 * Copyright (C) 2002-2006 Jean-Marc Valin.
 * BSD terms: vendor/speex-1.2.1/COPYING.
 * No heap, PLC, enhancer or general mode switching. Synthesis QMF is a
 * deliberately shorter 16-tap approximation; HB excitation/LPC remain exact. */
#include "speex_wb1.h"
#include "speex_avr.h"
#include "wb_internal.h"
#include "arch.h"
#include "lsp.h"
#include "wb_iir.h"
#include "wb_fold.h"
#include "zero_innovation.h"
#include "wb_qmf.h"
#include <string.h>
extern const int8_t high_lsp_cdbk[512],high_lsp_cdbk2[512],exc_10_32_table[320];
typedef struct {
    int16_t exc[40],old_lsp[8],lsp[8],den[8];
    int32_t mem[12];
    int16_t low[40],pcm[80];
    uint8_t qmf[64],gain[4],first,sub,error;
    speex_wb1_output_fn output;
    void *context;
} WbState;
static WbState wb;
/* Exact Xiph fixed-point spx_exp(256*(q-10)), q=0..31. */
static const int32_t exp_gain[32] AVR_TABLE={
    18772,21263,24091,27312,30954,35070,39734,45012,
    51006,57828,65536,74232,84108,95296,107996,122436,
    138728,157128,178048,201760,228656,259216,293648,332592,
    376928,427168,484128,548768,621536,704064,798048,904448};
void speex_wb1_init(void)
{speex_avr_init();memset(&wb,0,sizeof(wb));wb.first=1;}
size_t speex_wb1_state_bytes(void)
{return speex_avr_state_bytes()+sizeof(wb);}
int speex_wb1_decode(const uint8_t *packet,size_t bytes,speex_wb1_output_fn output,void *context)
{
    unsigned a,b,i;
    if(!packet || !output || bytes!=25 || (packet[0]>>3)!=3 || (packet[20]>>4)!=9)return -1;
    /* Validated HB1 layout: 6+6 LSP bits, then four 5-bit gains.
     * Direct byte windows need no generic cursor or cursor stack frame. */
    a=(((unsigned)(packet[20]&15)<<2)|(packet[21]>>6))*8;
    b=(unsigned)(packet[21]&63)*8;
    for(i=0;i<8;i++) {
        wb.lsp[i]=(int16_t)(6144+2560*i+32*(int16_t)AVR_READ_I8(high_lsp_cdbk+a+i)+16*(int16_t)AVR_READ_I8(high_lsp_cdbk2+b+i));
        if(wb.first)wb.old_lsp[i]=wb.lsp[i];
    }
    wb.gain[0]=packet[22]>>3;
    wb.gain[1]=((packet[22]&7)<<2)|(packet[23]>>6);
    wb.gain[2]=(packet[23]>>1)&31;
    wb.gain[3]=((packet[23]&1)<<4)|(packet[24]>>4);
    wb.output=output;wb.context=context;wb.sub=0;wb.error=0;
    int result=speex_wb_decode_low(packet);
    memcpy(wb.old_lsp,wb.lsp,sizeof(wb.lsp));wb.first=0;
    return wb.error?-2:result;
}
int16_t *speex_wb_low_buffer(void){return wb.low;}
SPEEX_NB3_STAGE void speex_wb_low_ready(const int16_t *low,const int16_t *low_den,const uint8_t *indices,int32_t scale)
{
    int16_t interp[8],ak[8];int32_t rl=8192,rh=8192,g;int16_t ratio;
    unsigned i,vector;
    if(wb.error)return;
    lsp_interpolate(wb.old_lsp,wb.lsp,interp,8,wb.sub,4,410);
    speex_wb_lsp8(interp,ak);
    for(i=0;i<8;i+=2)rh+=(int32_t)ak[i+1]-ak[i];
    for(i=0;i<10;i+=2)rl+=(int32_t)low_den[i+1]-low_den[i];
    if(rh+82<=0 || rl+82<=0) {wb.error=1;return;}
    ratio=(int16_t)SATURATE(PDIV32((rl+82)*128,82+rh),32767);
    if(ratio<=0) {wb.error=1;return;}
    g=PDIV32(AVR_READ_I32(exp_gain+wb.gain[wb.sub]),ratio);
    speex_wb_iir40(wb.exc,wb.den,wb.pcm+40,wb.mem);
    for(vector=0;vector<4;vector++) {
        const int8_t *shape=exc_10_32_table+10*indices[vector];
#if SPEEX_NB3_USE_AVR_ASM
        speex_avr_zero_innovation10(wb.exc+10*vector,shape,scale);
#else
        speex_nb3_zero_innovation_n_c(wb.exc+10*vector,shape,scale,10);
#endif
    }
    speex_wb_fold40(wb.exc,g);
    memcpy(wb.den,ak,sizeof(ak));
    speex_wb_qmf40(low,wb.pcm+40,wb.pcm,wb.qmf);
    wb.output(wb.pcm,80,wb.context);wb.sub++;
}
