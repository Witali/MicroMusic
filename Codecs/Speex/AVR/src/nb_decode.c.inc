/* Restricted NB3 body adapted from Xiph Speex 1.2.1 nb_celp.c.
 * Copyright (C) 2002-2006 Jean-Marc Valin; BSD terms in vendor/speex-1.2.1/COPYING.
 * Preserve the original excitation, interpolation, rounding and 40-sample
 * synthesis delay. Remove bookkeeping used only by unsupported PLC/enhancer
 * and general ctl APIs. The vendored release remains the independent oracle. */
__attribute__((noinline)) int nb_decode(void *state, SpeexBits *bits, void *vout)
{
   DecState *st=(DecState *)state;
   spx_word16_t *out=(spx_word16_t *)vout;
   char *stack=st->stack;
   int qe,sub,i,pitch;
   spx_word16_t pitch_gain[3];
   spx_word32_t ol_gain;
   VARDECL(spx_lsp_t *qlsp);
   VARDECL(spx_coef_t *ak);
   VARDECL(spx_word32_t *exc32);
   VARDECL(spx_lsp_t *interp_qlsp);
   if (!bits) return -2;
   st->exc=st->excBuf+NB_DEC_EXC_OFFSET;
   SPEEX_MOVE(st->excBuf,st->excBuf+NB_FRAME_SIZE,NB_DEC_SHIFT_COUNT);
   ALLOC(qlsp,NB_ORDER,spx_lsp_t);
   lsp_unquant_lbr(qlsp,NB_ORDER,bits);
   if (st->first) SPEEX_COPY(st->old_qlsp,qlsp,NB_ORDER);
   qe=speex_bits_unpack_unsigned(bits,5);
   ol_gain=MULT16_32_Q15(28406,ol_gain_table[qe]);
   ALLOC(ak,NB_ORDER,spx_coef_t);
   ALLOC(exc32,NB_SUBFRAME_SIZE,spx_word32_t);
   for (sub=0;sub<NB_NB_SUBFRAMES;sub++)
   {
      spx_word16_t *exc=st->exc+NB_SUBFRAME_SIZE*sub;
      int q_energy;
      spx_word32_t ener;
      /* Every pitch source index is negative: each segment ends before its
       * source reaches exc[0]. No clear of the current excitation is needed. */
      pitch_unquant_3tap(exc,exc32,NB_PITCH_START,NB_PITCH_END,0,&avr_ltp,
         NB_SUBFRAME_SIZE,&pitch,pitch_gain,bits,stack,0,NB_SUBFRAME_SIZE*sub,0,0);
      sanitize_values32(exc32,-QCONST32(32000,SIG_SHIFT-1),
                        QCONST32(32000,SIG_SHIFT-1),NB_SUBFRAME_SIZE);
      q_energy=speex_bits_unpack_unsigned(bits,1);
      ener=MULT16_32_Q14(exc_gain_quant_scal1[q_energy],ol_gain);
      speex_avr_innovation(exc,exc32,bits,ener);
   }
   ALLOC(interp_qlsp,NB_ORDER,spx_lsp_t);
   SPEEX_COPY(out,&st->exc[-NB_SUBFRAME_SIZE],NB_FRAME_SIZE);
   for (sub=0;sub<NB_NB_SUBFRAMES;sub++)
   {
      spx_word16_t *sp=out+NB_SUBFRAME_SIZE*sub;
      lsp_interpolate(st->old_qlsp,qlsp,interp_qlsp,NB_ORDER,sub,
                      NB_NB_SUBFRAMES,LSP_MARGIN);
      lsp_to_lpc(interp_qlsp,ak,NB_ORDER,stack);
      iir_mem16(sp,st->interp_qlpc,sp,NB_SUBFRAME_SIZE,NB_ORDER,st->mem_sp,stack);
      for (i=0;i<NB_ORDER;i++) st->interp_qlpc[i]=ak[i];
#ifdef SPEEX_AVR_OUTPUT_HOOK
      {
         extern void speex_avr_output(const spx_word16_t *,uint8_t);
         speex_avr_output(sp,NB_SUBFRAME_SIZE);
      }
#endif
   }
   SPEEX_COPY(st->old_qlsp,qlsp,NB_ORDER);
   st->first=0;
   return 0;
}
