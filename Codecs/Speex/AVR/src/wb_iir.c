/* Exact order-eight direct form of Xiph's transposed IIR, including the
 * coefficient-age transition. Forty samples return the history cursor to 0.
 * State: eight negative outputs twice, followed by eight coefficient ages. */
#include "wb_iir.h"
SPEEX_NB3_HOT void speex_wb_iir40_c(const int16_t *x,const int16_t *den,
                                  int16_t *out,int32_t *mem)
{
    int16_t *history=(int16_t *)mem,*ages=history+16;
    unsigned i,j,pos=0;
    for(i=0;i<40;i++) {
        uint32_t sum=0;
        for(j=0;j<8;j++)sum+=(uint32_t)((int32_t)ages[j]*history[pos+7-j]);
        int32_t v=(int32_t)x[i]+((int32_t)(sum+4096)>>13);
        int16_t y=v>32767?32767:v< -32767?-32767:(int16_t)v;
        out[i]=y;history[pos]=history[pos+8]=-y;
        if(++pos==8)pos=0;
        if(i<8)ages[i]=den[i];
    }
}
