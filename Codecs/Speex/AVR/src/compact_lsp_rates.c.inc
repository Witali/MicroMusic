/* Exact symmetric fixed-point Xiph recurrence for LPC orders 8 and 10.
 * Bounded half-polynomials replace the upstream quadratic scratch matrices.
 * Xiph arithmetic/rounding and all subframe interpolations are preserved. */
void lsp_to_lpc(const spx_lsp_t *freq, spx_coef_t *ak, int lpcrdr, char *stack)
{
    spx_word32_t p[6]={1048576},q[6]={1048576};
    spx_word32_t previous_p=0,previous_q=0;
    int stage,j,m=lpcrdr/2;
    (void)stack;
    for (stage=0;stage<m;++stage) {
        spx_word16_t fp=ANGLE2X(freq[2*stage]);
        spx_word16_t fq=ANGLE2X(freq[2*stage+1]);
        for (j=stage+1;j>=1;--j) {
            spx_word32_t ap=j<=stage?p[j]:(stage?p[stage-1]:0);
            spx_word32_t aq=j<=stage?q[j]:(stage?q[stage-1]:0);
            spx_word32_t pp=j>=2?p[j-2]:0;
            spx_word32_t qq=j>=2?q[j-2]:0;
            p[j]=ADD32(SUB32(ap,MULT16_32_Q14(fp,p[j-1])),pp);
            q[j]=ADD32(SUB32(aq,MULT16_32_Q14(fq,q[j-1])),qq);
        }
    }
    for (j=1;j<=lpcrdr;++j) {
        int index=j<=m?j:lpcrdr-j;
        spx_word32_t a=PSHR32(p[index]+previous_p+q[index]-previous_q,8);
        previous_p=p[index];previous_q=q[index];
        if (a < -32767) a=-32767;
        if (a > 32767) a=32767;
        ak[j-1]=(spx_coef_t)a;
    }
}
