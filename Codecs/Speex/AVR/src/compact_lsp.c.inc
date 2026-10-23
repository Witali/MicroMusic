/* Exact symmetric form of the Xiph fixed-point polynomial recurrence.
 * Each polynomial is palindromic; retain coefficients 0..5 of order 10.
 * Reversed terms use identical rounded products and modulo-32 additions.
 * All four per-frame LSP interpolations/conversions are retained. Peel the
 * symmetric endpoints and p[0]==2^20 product; constant stages remove bounds
 * branches and pointer arithmetic in exchange for additional Flash. */
static inline __attribute__((always_inline)) void lsp_stage(spx_word32_t *p, spx_word16_t f, int stage)
{
    int j;
    p[stage+1] = SUB32(SHL32(p[stage-1],1), MULT16_32_Q14(f,p[stage]));
    for (j=stage;j>=2;--j)
        p[j] = ADD32(SUB32(p[j], MULT16_32_Q14(f,p[j-1])),p[j-2]);
    p[1] = SUB32(p[1],SHL32(EXTEND32(f),6));
}
#ifdef __AVR__
#define STAGE_ATTR __attribute__((noinline,noclone))
#else
#define STAGE_ATTR __attribute__((noinline))
#endif
static STAGE_ATTR spx_word16_t lsp_angle(spx_lsp_t angle) {return ANGLE2X(angle);}
#define DEFINE_STAGE(s) static STAGE_ATTR void lsp_stage##s(spx_word32_t *p, spx_word16_t f) {lsp_stage(p,f,s);}
DEFINE_STAGE(1)
DEFINE_STAGE(2)
DEFINE_STAGE(3)
DEFINE_STAGE(4)
#undef DEFINE_STAGE
#undef STAGE_ATTR
void lsp_to_lpc(const spx_lsp_t *freq, spx_coef_t *ak, int lpcrdr, char *stack)
{
    spx_word32_t p[6], q[6];
    spx_word32_t previous_p = 0, previous_q = 0;
    int j;
    (void)lpcrdr;
    (void)stack;
    p[0]=q[0]=1048576;
    p[1]=-SHL32(EXTEND32(lsp_angle(freq[0])),6);
    q[1]=-SHL32(EXTEND32(lsp_angle(freq[1])),6);
#define STAGE(s) lsp_stage##s(p,lsp_angle(freq[2*s])); lsp_stage##s(q,lsp_angle(freq[2*s+1]))
    STAGE(1); STAGE(2); STAGE(3); STAGE(4);
#undef STAGE
    for (j = 1; j <= 10; ++j) {
        int index = j <= 5 ? j : 10-j;
        spx_word32_t a = PSHR32(p[index] + previous_p + q[index] - previous_q, 8);
        previous_p = p[index];
        previous_q = q[index];
        if (a < -32767) a = -32767;
        if (a > 32767) a = 32767;
        ak[j-1] = (spx_coef_t)a;
    }
}
