#include "nb3_header.h"
#include "nb3_subframe.h"
#include "nb3_lsp.h"
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
    const int16_t *in,const uint8_t *input_indices,int32_t scale,unsigned index)
{
#if SPEEX_NB3_USE_AVR_ASM
    const uint8_t *indices=input_indices;
#else
    uint8_t indices[4];
    for(unsigned k=0;k<4;k++)indices[k]=input_indices[k];
#endif
    int8_t gains[3];
    uint8_t vector;
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
SPEEX_NB3_HOT SPEEX_NB3_NOINLINE int nb_decode(void *state, const uint8_t *packet, void *vout)
{
   DecState *st=(DecState *)state;
   spx_word16_t *out=(spx_word16_t *)vout;
   spx_word16_t *frame_exc=st->excBuf+NB_DEC_EXC_OFFSET;
   char *stack=st->stack;
   int qe,sub,i;
   uint8_t repeat_lsp;
   VARDECL(spx_lsp_t *lsp_delta);
   VARDECL(spx_coef_t *ak);
   VARDECL(spx_lsp_t *interp_qlsp);
   VARDECL(uint8_t *indices);
   if (!packet) return -2;
   SPEEX_MOVE(st->excBuf,st->excBuf+NB_FRAME_SIZE,NB_DEC_SHIFT_COUNT);
   ALLOC(lsp_delta,NB_ORDER,spx_lsp_t);
   repeat_lsp=st->first || (st->lsp_key[0]==(packet[0]&7) &&
                  st->lsp_key[1]==packet[1] && st->lsp_key[2]==(packet[2]&254));
   if (st->first || !repeat_lsp) {
      /* Decode directly in quarter units. The original two P14 products
       * are integral for NB3's multiple-of-16 endpoints. Prepare the same
       * delta before excitation, avoiding a raw-angle temporary round trip. */
      speex_nb3_lsp_quarters(packet,lsp_delta);
      if(st->first) for(i=0;i<NB_ORDER;i++) {st->old_qlsp[i]=4*lsp_delta[i];lsp_delta[i]=0;}
      else for(i=0;i<NB_ORDER;i++)lsp_delta[i]-=st->old_qlsp[i]>>2;
      st->lsp_key[0]=packet[0]&7;st->lsp_key[1]=packet[1];st->lsp_key[2]=packet[2]&254;
   }
   qe=speex_nb3_frame_gain(packet);
   /* The validated packet map supplies the complete 33-bit group once.
    * This four-byte slot is dead when LPC synthesis reuses offset 20. */
   ALLOC(indices,4,uint8_t);
   for (sub=0;sub<NB_NB_SUBFRAMES;sub++)
   {
      spx_word16_t *exc=frame_exc+NB_SUBFRAME_SIZE*sub;
      uint16_t header=speex_nb3_unpack_subframe(packet,(uint8_t)sub,indices);
      unsigned pitch=(header>>6)+17;
      unsigned index=((header>>1)&31)*4;
      int q_energy;
      spx_word32_t ener;
      /* Every pitch source index is negative: each segment ends before its
       * source reaches exc[0]. No clear of the current excitation is needed. */
      q_energy=header&1;
      ener=AVR_READ_I32(&nb3_gain_table[(qe<<1)|q_energy]);
      if (!index) {
         speex_nb3_zero_innovation(exc,indices,ener);
      } else if (pitch>=41) {
         /* Even the last tap reads exc[-1] or earlier. No output feeds a
          * source in this block; fuse the three sums with innovation. */
         speex_nb3_long_innovation(exc,exc-pitch-1,indices,ener,index);
      } else {
         speex_nb3_short_innovation(exc,exc,(uint8_t)pitch,indices,ener,index);
      }
   }
   /* Release the excitation indices. C shares the next 20 B between angles
    * and LPC; ASM uses only three temporary center angles in that slot.
    * Both converters consume all frequencies before coefficient stores.
    * LPC enters state before WB reuses this slot for callback indices. */
   stack=(char *)(lsp_delta+NB_ORDER);
   ALLOC(ak,NB_ORDER,spx_coef_t);
   interp_qlsp=ak;
   /* The delta was prepared before excitation. Cache hits do not read it;
    * changed frames advance raw state four times, with margin only on out. */
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
#if SPEEX_NB3_USE_AVR_ASM
         speex_nb3_interpolate_lpc(st->old_qlsp,lsp_delta,ak);
#else
         speex_nb3_interpolate_codebook(st->old_qlsp,lsp_delta,interp_qlsp);
         lsp_to_lpc(interp_qlsp,ak,NB_ORDER,stack);
#endif
      }
      /* Excitation is complete and remains read-only during synthesis.
       * Filter from its delayed history directly, retaining the original
       * 40-sample delay without copying a whole frame into the PCM output. */
      iir_mem16(frame_exc-NB_SUBFRAME_SIZE+NB_SUBFRAME_SIZE*sub,
                st->interp_qlpc,sp,NB_SUBFRAME_SIZE,NB_ORDER,st->mem_sp,stack);
      if (update_lpc) for (i=0;i<NB_ORDER;i++) st->interp_qlpc[i]=ak[i];
#if SPEEX_ENABLE_WB1
      if (!out) {
         uint16_t header;
         /* Interpolated angles are dead once LPC is ready. HB consumes the
          * reconstructed indices synchronously, before the next quarter. */
         indices=(uint8_t *)interp_qlsp;
         header=speex_nb3_unpack_subframe(packet,(uint8_t)sub,indices);
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
