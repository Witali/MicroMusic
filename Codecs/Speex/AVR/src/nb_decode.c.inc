#include "nb3_header.h"
#if SPEEX_ENABLE_WB1
#include "wb_internal.h"
#endif
#include "nb3_indices.h"
#include "nb3_interpolate.h"
/* Restricted NB3 body adapted from Xiph Speex 1.2.1 nb_celp.c.
 * Copyright (C) 2002-2006 Jean-Marc Valin; BSD terms in vendor/speex-1.2.1/COPYING.
 * Preserve the original excitation, interpolation, rounding and 40-sample
 * synthesis delay. Remove bookkeeping used only by unsupported PLC/enhancer
 * and general ctl APIs. The vendored release remains the independent oracle. */
#include "speex_platform.h"
#include "pitch24.h"
#include "long_pitch.h"
#include "short_pitch.h"
#if SPEEX_NB3_USE_AVR_ASM
static SPEEX_NB3_NOINLINE
#else
static SPEEX_NB3_STAGE_O2
#endif
void speex_nb3_long_innovation(int16_t *out,
    const int16_t *in,SpeexBits *bits,int32_t scale,unsigned index)
{
    int8_t gains[3];
    uint8_t vector;
    uint8_t indices[4];
    speex_nb3_unpack_indices(bits,indices);
    gains[0]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+2));
    gains[1]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index+1));
    gains[2]=(int8_t)(32+AVR_READ_I8(gain_cdbk_lbr+index));
#if SPEEX_NB3_USE_AVR_ASM
    speex_avr_long_innovation40(out,in,indices,scale,gains);
#else
    for (vector=0;vector<4;vector++) {
        unsigned code=indices[vector];
        const int8_t *shape=exc_10_32_table+10*code;
        speex_nb3_long_innovation10_c(out,in,shape,scale,gains,10);
        out+=10;in+=10;
    }
#endif
}
_Static_assert(NB_SUBFRAME_SIZE==40 && NB_PITCH_START==17 && NB_PITCH_END==144,
               "Packed pitch is specialized for the pinned NB3 frame/pitch bounds");
_Static_assert(NB_ORDER==10 && NB_NB_SUBFRAMES==4 && LSP_MARGIN==16,
               "Quarter-step LSP interpolation requires the pinned NB3 geometry");
SPEEX_NB3_HOT SPEEX_NB3_NOINLINE int nb_decode(void *state, SpeexBits *bits, void *vout)
{
   DecState *st=(DecState *)state;
   spx_word16_t *out=(spx_word16_t *)vout;
   spx_word16_t *frame_exc=st->excBuf+NB_DEC_EXC_OFFSET;
   char *stack=st->stack;
   int qe,sub,i;
   uint8_t repeat_lsp;
   const uint8_t *packet;
   VARDECL(spx_lsp_t *qlsp);
   VARDECL(spx_coef_t *ak);
   VARDECL(spx_lsp_t *interp_qlsp);
   if (!bits) return -2;
   packet=(const uint8_t *)bits->chars;
   SPEEX_MOVE(st->excBuf,st->excBuf+NB_FRAME_SIZE,NB_DEC_SHIFT_COUNT);
   ALLOC(qlsp,NB_ORDER,spx_lsp_t);
   repeat_lsp=st->first || (st->lsp_key[0]==(packet[0]&7) &&
                  st->lsp_key[1]==packet[1] && st->lsp_key[2]==(packet[2]&254));
   if (!st->first && repeat_lsp) {
      /* Validated raw NB3 packets start at bit 5. Three 6-bit LSP fields
       * finish at bit 23. Gain bit 23 is deliberately excluded from the key. */
      bits->charPtr=2;bits->bitPtr=7;
      SPEEX_COPY(qlsp,st->old_qlsp,NB_ORDER);
   } else {
      lsp_unquant_lbr(qlsp,NB_ORDER,bits);
      st->lsp_key[0]=packet[0]&7;st->lsp_key[1]=packet[1];st->lsp_key[2]=packet[2]&254;
   }
   if (st->first) SPEEX_COPY(st->old_qlsp,qlsp,NB_ORDER);
   qe=speex_bits_unpack_unsigned(bits,5);
   for (sub=0;sub<NB_NB_SUBFRAMES;sub++)
   {
      spx_word16_t *exc=frame_exc+NB_SUBFRAME_SIZE*sub;
      uint16_t header=speex_nb3_unpack_header(bits);
      unsigned pitch=(header>>6)+17;
      unsigned index=((header>>1)&31)*4;
      int q_energy;
      spx_word32_t ener;
      /* Every pitch source index is negative: each segment ends before its
       * source reaches exc[0]. No clear of the current excitation is needed. */
      q_energy=header&1;
      ener=AVR_READ_I32(&nb3_gain_table[(qe<<1)|q_energy]);
      if (!index) {
         speex_nb3_zero_innovation(exc,bits,ener);
      } else if (pitch>=41) {
         /* Even the last tap reads exc[-1] or earlier. No output feeds a
          * source in this block; fuse the three sums with innovation. */
         speex_nb3_long_innovation(exc,exc-pitch-1,bits,ener,index);
      } else {
         speex_nb3_short_innovation(exc,exc,(uint8_t)pitch,bits,ener,index);
      }
   }
   /* Excitation uses no scratch beyond qlsp. Allocate distinct synthesis
    * arrays after it, retaining the four original interpolation steps. */
   ALLOC(ak,NB_ORDER,spx_coef_t);
   ALLOC(interp_qlsp,NB_ORDER,spx_lsp_t);
   /* Reuse the raw-endpoint scratch for a constant quarter-frame delta.
    * On reset old_qlsp already equals qlsp, giving zero deltas. A changed
    * frame advances old_qlsp four times; margin corrections touch only out. */
   if (!repeat_lsp || st->first) for(i=0;i<NB_ORDER;i++)
      qlsp[i]=(qlsp[i]>>2)-(st->old_qlsp[i]>>2);
   for (sub=0;sub<NB_NB_SUBFRAMES;sub++)
   {
      spx_word16_t *sp;
#if SPEEX_ENABLE_WB1
      sp=out?out+NB_SUBFRAME_SIZE*sub:speex_wb_low_buffer();
#else
      sp=out+NB_SUBFRAME_SIZE*sub;
#endif
      uint8_t update_lpc=!repeat_lsp || (st->first && !sub);
      /* NB3 unquantized angles are multiples of 16. Its quarter-step P14
       * products are exact even though upstream rounds the two products
       * separately. Equal endpoints therefore produce identical margin-
       * adjusted angles in all four steps. The last LPC is already cached.
       * On reset, compute it after the first synthesis step as upstream does.
       * IIR always runs, including its coefficient-age transition. */
      if (update_lpc) {
         speex_nb3_interpolate(st->old_qlsp,qlsp,interp_qlsp);
         lsp_to_lpc(interp_qlsp,ak,NB_ORDER,stack);
      }
      /* Excitation is complete and remains read-only during synthesis.
       * Filter from its delayed history directly, retaining the original
       * 40-sample delay without copying a whole frame into the PCM output. */
      iir_mem16(frame_exc-NB_SUBFRAME_SIZE+NB_SUBFRAME_SIZE*sub,
                st->interp_qlpc,sp,NB_SUBFRAME_SIZE,NB_ORDER,st->mem_sp,stack);
      if (update_lpc) for (i=0;i<NB_ORDER;i++) st->interp_qlpc[i]=ak[i];
#if SPEEX_ENABLE_WB1
      if (!out) {
         SpeexBits cursor={0};
         uint8_t indices[4];
         uint16_t header;
         cursor.nbBits=160;cursor.chars=(char *)packet;cursor.charPtr=3+4*sub;cursor.bitPtr=4+sub;
         header=speex_nb3_unpack_header(&cursor);
         speex_nb3_unpack_indices(&cursor,indices);
         speex_wb_low_ready(sp,st->interp_qlpc,indices,
             AVR_READ_I32(nb3_gain_table+(qe<<1)+(header&1)));
      }
#endif
#ifdef SPEEX_AVR_OUTPUT_HOOK
      {
         extern void speex_avr_output(const spx_word16_t *,uint8_t);
#if SPEEX_ENABLE_WB1
         if (out)
#endif
         speex_avr_output(sp,NB_SUBFRAME_SIZE);
      }
#endif
   }
   st->first=0;
   return 0;
}
