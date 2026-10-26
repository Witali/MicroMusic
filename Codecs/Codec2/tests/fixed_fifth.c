#include "fixed_fifth.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static float from_bits(uint32_t u){float f;memcpy(&f,&u,4);return f;}
int main(void){
    double maximum=0;uint32_t worst=0;unsigned count=0;
    float previous=0;
    for(uint32_t e=0;e<255;++e)for(uint32_t m=0;m<4096;++m){
        uint32_t bits=(e<<23)|(m<<11);
        if(!bits)continue;
        float x=from_bits(bits),actual=codec2_fixed_fifth(x),reference=powf(x,.2f);
        assert(isfinite(actual)&&actual>0&&actual>=previous);previous=actual;
        double error=fabs((double)actual/reference-1);
        if(error>maximum){maximum=error;worst=bits;}++count;
    }
    for(unsigned k=0;k<23;++k)for(int d=-1;d<=1;++d){
        uint32_t bits=(UINT32_C(1)<<k)+d;if(!bits)continue;
        float x=from_bits(bits),a=codec2_fixed_fifth(x),r=powf(x,.2f);
        double error=fabs((double)a/r-1);if(error>maximum){maximum=error;worst=bits;}++count;
    }
    assert(codec2_fixed_fifth(0)==0&&codec2_fixed_fifth(-0.0f)==0);
    assert(isnan(codec2_fixed_fifth(-1))&&isnan(codec2_fixed_fifth(NAN))&&isinf(codec2_fixed_fifth(INFINITY)));
    printf("{\"inputs\":%u,\"maximum_relative_error\":%.12g,\"worst_input_bits\":%u}\n",count,maximum,worst);
    return 0;
}
