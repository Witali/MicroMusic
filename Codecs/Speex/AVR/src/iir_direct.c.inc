/* NB3-only exact direct-form synthesis. The 60-byte zero-initialized state
 * holds 10 negative outputs twice, followed by 10 coefficient ages. A call
 * processes exactly 40 samples, so the history cursor returns to zero.
 * Changing coefficients one tap per sample preserves the original transposed
 * filter's first ten outputs after each coefficient change. */
#include "speex_platform.h"
#if SPEEX_NB3_USE_AVR_ASM
extern void speex_avr_iir40(const int16_t *, const int16_t *, int16_t *, int32_t *);
#else
static int32_t speex_avr_lpc_dot10(const int16_t *coef, const int16_t *after)
{
   uint32_t sum = 0;
   int j;
   for (j=0;j<10;j++)
      sum += (uint32_t)((int32_t)coef[j] * *--after);
   return (int32_t)sum;
}
#endif

SPEEX_NB3_NOINLINE void iir_mem16(const spx_word16_t *x,
   const spx_coef_t *den, spx_word16_t *y, int N, int ord,
   spx_mem_t *mem, char *stack)
{
#if SPEEX_NB3_USE_AVR_ASM
   (void)N; (void)ord; (void)stack;
   speex_avr_iir40(x, den, y, mem);
#else
   int16_t *history = (int16_t *)mem;
   int16_t *coef = history+20;
   uint8_t i, pos=0;
   (void)N; (void)ord; (void)stack;
   for (i=0;i<40;i++)
   {
      int32_t sum = speex_avr_lpc_dot10(coef, history+pos+10);
      spx_word16_t yi = EXTRACT16(SATURATE(ADD32(EXTEND32(x[i]),
                            PSHR32(sum,LPC_SHIFT)),32767));
      spx_word16_t nyi = NEG16(yi);
      y[i] = yi;
      history[pos] = history[pos+10] = nyi;
      if (++pos == 10) pos=0;
      if (i<10) coef[i]=den[i];
   }
#endif
}
