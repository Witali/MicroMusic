/* NB3 state subset of Xiph Speex 1.2.1 nb_celp.h.
 * Copyright (C) 2002-2006 Jean-Marc Valin; BSD terms in vendor/speex-1.2.1/COPYING.
 * No PLC, enhancer, level queries, highpass or vocoder state is observable
 * through the restricted API. The pinned original structure remains vendored. */
typedef struct DecState {
   int first;
   char *stack;
   spx_word16_t excBuf[NB_DEC_BUFFER];
   spx_word16_t *exc;
   spx_lsp_t old_qlsp[NB_ORDER];
   spx_coef_t interp_qlpc[NB_ORDER];
   spx_mem_t mem_sp[15]; /* 60-byte direct LPC history and coefficient ages */
} DecState;
