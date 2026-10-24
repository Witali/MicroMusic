#include "wb_fold.h"
/* g is the original nonnegative HB1 exp gain divided by the filter ratio.
 * PSHR14(SHL14(P15(t,SHL6(g)))) has the same low16 as (t*g+256)>>9.
 * Keeping only those bits removes a 160-byte signed32 excitation buffer.
 * Delaying this signed16 excitation by 40 samples preserves Xiph's timing. */
SPEEX_NB3_HOT void speex_wb_fold40_c(int16_t *exc,int32_t g)
{
    unsigned i;
    for(i=0;i<40;i++) {
        int16_t t=(int16_t)(((int32_t)29491*exc[i])>>15);
        uint32_t product=(uint32_t)t*(uint32_t)g+256;
        uint16_t v=(uint16_t)(product>>9);
        exc[i]=(int16_t)((i&1)?(uint16_t)(0u-v):v);
    }
}
