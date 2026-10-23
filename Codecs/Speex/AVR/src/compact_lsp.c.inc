/* Exact symmetric form of the Xiph fixed-point polynomial recurrence.
 * Each polynomial is palindromic; retain coefficients 0..5 of order 10.
 * Reversed terms use identical rounded products and modulo-32 additions.
 * All four per-frame LSP interpolations/conversions are retained. Peel the
 * symmetric endpoints and p[0]==2^20 product; constant stages remove bounds
 * branches and pointer arithmetic in exchange for additional Flash. */
#include "speex_platform.h"
#if SPEEX_NB3_USE_AVR_ASM
extern int32_t speex_avr_lsp_mul_q14(int16_t,int32_t);
#define LSP_Q14(a,b) speex_avr_lsp_mul_q14(a,b)
#else
#define LSP_Q14(a,b) MULT16_32_Q14(a,b)
#endif
/* |f|<=32768, so |Q14(f,x)|<=2*|x|+1. Starting at 2^20/2^21,
 * the four stages bound their largest product inputs by
 * 2097152, 6291457, 20971523, 73400331, all below 2^29.
 * Thus the fast signed30 entry exactly matches the generic high-word cast. */
static SPEEX_NB3_ALWAYS_INLINE void lsp_stage(spx_word32_t *p, spx_word16_t f, int stage)
{
    int j;
    p[stage+1] = SUB32(SHL32(p[stage-1],1), LSP_Q14(f,p[stage]));
    for (j=stage;j>=2;--j)
        p[j] = ADD32(SUB32(p[j], LSP_Q14(f,p[j-1])),p[j-2]);
    p[1] = SUB32(p[1],SHL32(EXTEND32(f),6));
}
#define STAGE_ATTR SPEEX_NB3_STAGE
static STAGE_ATTR spx_word16_t lsp_angle(spx_lsp_t angle) {return ANGLE2X(angle);}
/* The first two roots give p1=-(a+b)*64 and p2=2^21+ceil(a*b/256).
 * Fold the constant and ceil bias before the byte-aligned >>8. The sum
 * stays inside signed32 for all signed16 a/b, including both extrema. */
static STAGE_ATTR void lsp_first(spx_word32_t *p,spx_word16_t a,spx_word16_t b)
{
    p[1]=-ADD32(EXTEND32(a),EXTEND32(b))*64;
    p[2]=SHR32(ADD32(MULT16_16(a,b),536871167),8);
}
#define DEFINE_STAGE(s) static STAGE_ATTR void lsp_stage##s(spx_word32_t *p, spx_word16_t f) {lsp_stage(p,f,s);}
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
    lsp_first(p,lsp_angle(freq[0]),lsp_angle(freq[2]));
    lsp_first(q,lsp_angle(freq[1]),lsp_angle(freq[3]));
#define STAGE(s) lsp_stage##s(p,lsp_angle(freq[2*s])); lsp_stage##s(q,lsp_angle(freq[2*s+1]))
    STAGE(2); STAGE(3); STAGE(4);
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
