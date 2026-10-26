/* Exact symmetric form of the Xiph fixed-point polynomial recurrence.
 * Each polynomial is palindromic; retain coefficients 0..5 of order 10.
 * Reversed terms use identical rounded products and modulo-32 additions.
 * All four per-frame LSP interpolations/conversions are retained. Peel the
 * symmetric endpoints and p[0]==2^20 product; constant stages remove bounds
 * branches and pointer arithmetic in exchange for additional Flash. */
#include "speex_platform.h"
#include "nb3_lsp_stage.h"
#include "nb3_lsp_first.h"
#include "nb3_lsp_pair.h"
#define STAGE_ATTR SPEEX_NB3_STAGE
#if SPEEX_NB3_USE_AVR_ASM
#include "nb3_lsp_angle.h"
#define lsp_angle speex_nb3_lsp_angle
#else
static STAGE_ATTR spx_word16_t lsp_angle(spx_lsp_t angle) {return ANGLE2X(angle);}
#endif
/* The first two roots give p1=-(a+b)*64 and p2=2^21+ceil(a*b/256).
 * Fold the constant and ceil bias before the byte-aligned >>8. The sum
 * stays inside signed32 for all signed16 a/b, including both extrema. */
static STAGE_ATTR void lsp_first(spx_word32_t *p,spx_word16_t a,spx_word16_t b)
{
    speex_nb3_lsp_first(p,a,b);
}
#define DEFINE_STAGE(s) static STAGE_ATTR void lsp_stage##s(spx_word32_t *p, spx_word16_t f) {speex_nb3_lsp_stage##s(p,f);}
DEFINE_STAGE(2)
DEFINE_STAGE(3)
DEFINE_STAGE(4)
#undef DEFINE_STAGE
#if SPEEX_NB3_USE_AVR_ASM
#define LSP_PAIR(n,p,q,fp,fq) speex_nb3_lsp_pair##n(p,q,fp,fq)
#else
#define LSP_PAIR(n,p,q,fp,fq) lsp_stage##n(p,fp);lsp_stage##n(q,fq)
#endif
#undef STAGE_ATTR
#include "nb3_lsp_finish.h"
/* The generic converter retains the explicitly selectable C body. The fused
 * decoder uses the architecture-selected kernel through its shared stage. */
static SPEEX_NB3_ALWAYS_INLINE void lsp_finish10_c(const spx_word32_t *restrict p,
    const spx_word32_t *restrict q,spx_coef_t *restrict ak)
{
    speex_nb3_lsp_finish10_c(p,q,ak);
}

static SPEEX_NB3_STAGE void lsp_finish10(const spx_word32_t *restrict p,
    const spx_word32_t *restrict q,spx_coef_t *restrict ak)
{
    speex_nb3_lsp_finish10(p,q,ak);
}

SPEEX_NB3_HOT void lsp_to_lpc(const spx_lsp_t *freq, spx_coef_t *ak, int lpcrdr, char *stack)
{
    spx_word32_t p[6],q[6];
    (void)lpcrdr;(void)stack;
    p[0]=q[0]=1048576;
    lsp_first(p,lsp_angle(freq[0]),lsp_angle(freq[2]));
    lsp_first(q,lsp_angle(freq[1]),lsp_angle(freq[3]));
#define STAGE(s) LSP_PAIR(s,p,q,lsp_angle(freq[2*s]),lsp_angle(freq[2*s+1]))
    STAGE(2); STAGE(3); STAGE(4);
#undef STAGE
    lsp_finish10_c(p,q,ak);
}

#include "nb3_interpolate.h"
/* The output area first holds only three center frequencies. Consume all
 * of them in the polynomial stages before lsp_finish10 writes coefficients.
 * raw/delta/ak are disjoint. ASM requires the normal explicit target opt-in;
 * its advance operation has the selectable C implementation in the header. */
SPEEX_NB3_STAGE void speex_nb3_interpolate_lpc(
    int16_t *restrict raw,const int16_t *restrict delta,int16_t *restrict ak)
{
    spx_word32_t p[6],q[6];
    speex_nb3_advance_codebook(raw,delta,ak);
    p[0]=q[0]=1048576;
    lsp_first(p,lsp_angle(raw[0]),lsp_angle(raw[2]));
    lsp_first(q,lsp_angle(raw[1]),lsp_angle(ak[0]));
    LSP_PAIR(2,p,q,lsp_angle(ak[1]),lsp_angle(ak[2]));
    LSP_PAIR(3,p,q,lsp_angle(raw[6]),lsp_angle(raw[7]));
    LSP_PAIR(4,p,q,lsp_angle(raw[8]),lsp_angle(raw[9]));
    lsp_finish10(p,q,ak);
}

#if SPEEX_ENABLE_WB1
void speex_wb_lsp8(const spx_lsp_t *freq,spx_coef_t *ak)
{
    spx_word32_t p[5],q[5],previous_p=0,previous_q=0;
    int j;
    p[0]=q[0]=1048576;
    lsp_first(p,lsp_angle(freq[0]),lsp_angle(freq[2]));
    lsp_first(q,lsp_angle(freq[1]),lsp_angle(freq[3]));
    LSP_PAIR(2,p,q,lsp_angle(freq[4]),lsp_angle(freq[5]));
    LSP_PAIR(3,p,q,lsp_angle(freq[6]),lsp_angle(freq[7]));
    for(j=1;j<=8;j++) {
        int index=j<=4?j:8-j;
        spx_word32_t a=PSHR32(p[index]+previous_p+q[index]-previous_q,8);
        previous_p=p[index];previous_q=q[index];
        if(a< -32767)a=-32767;if(a>32767)a=32767;ak[j-1]=(int16_t)a;
    }
}
#endif

#undef LSP_PAIR
