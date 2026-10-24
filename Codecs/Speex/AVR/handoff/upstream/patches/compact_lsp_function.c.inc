/* Memory-compact, bit-exact candidate for Xiph Speex fixed-point
 * lsp_to_lpc(). NB order 10 ONLY. Uses the original Speex arithmetic
 * macros, including its 16x32 multiply and rounding behavior.
 * P(z),Q(z) are formed in-place by multiplying quadratic factors.
 * This version deliberately keeps EVERY per-subframe LSP->LPC update.
 */
void lsp_to_lpc(const spx_lsp_t *freq, spx_coef_t *ak, int lpcrdr, char *stack)
{
   spx_word32_t p[11] = {0};
   spx_word32_t q[11] = {0};
   spx_word32_t previous_p = 0, previous_q = 0;
   const spx_word32_t xin = SHL32(EXTEND32(1), 20); /* QIMP=21 */
   int stage, j;
   (void)lpcrdr; /* restricted NB 10-pole build, DISABLE_WIDEBAND */
   (void)stack;
   p[0] = xin;
   q[0] = xin;
   for (stage = 0; stage < 5; ++stage)
   {
      int degree = 2 * stage;
      spx_word16_t fp = ANGLE2X(freq[2 * stage]);
      spx_word16_t fq = ANGLE2X(freq[2 * stage + 1]);
      /* Highest coefficient remains xin for every quadratic section. */
      p[degree + 2] = p[degree];
      q[degree + 2] = q[degree];
      /* Descending update preserves the still-needed old coefficients. */
      for (j = degree + 1; j >= 1; --j)
      {
         spx_word32_t ap = (j <= degree) ? p[j] : 0;
         spx_word32_t aq = (j <= degree) ? q[j] : 0;
         spx_word32_t pp = (j >= 2) ? p[j - 2] : 0;
         spx_word32_t qq = (j >= 2) ? q[j - 2] : 0;
         p[j] = ADD32(SUB32(ap, MULT16_32_Q14(fp, p[j - 1])), pp);
         q[j] = ADD32(SUB32(aq, MULT16_32_Q14(fq, q[j - 1])), qq);
      }
   }
   for (j = 1; j <= 10; ++j)
   {
      spx_word32_t a = PSHR32(p[j] + previous_p + q[j] - previous_q, 8);
      previous_p = p[j];
      previous_q = q[j];
      if (a < -32767) a = -32767;
      if (a > 32767) a = 32767;
      ak[j - 1] = (spx_coef_t)a;
   }
}
