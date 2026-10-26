/* Zero/basis, high-order cancellation and random LPC-like inputs. */
#include "fixed_analysis.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
static uint32_t seed=1;
static float next(void){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);return ((int32_t)(seed>>8)-8388608)/65536.0f;}
int main(int argc,char **argv){
    assert(argc==3);FILE *input=fopen(argv[1],"wb"),*expected=fopen(argv[2],"wb");assert(input&&expected);
    const float polynomial[11]={1,-10,45,-120,210,-252,210,-120,45,-10,1};
    for(unsigned trial=0;trial<64;++trial){
        float a[11],scale=ldexpf(1,(int)(trial%33)-16);compact_transform output;
        for(unsigned i=0;i<11;++i){float value=trial==0?0:trial<=11?(float)(i==trial-1):trial==12?polynomial[i]:trial==13?((i&1)?-polynomial[i]:polynomial[i]):i==0?1:next();a[i]=value*scale;}
        codec2_analysis_forward(&output,a);assert(fwrite(a,sizeof(a),1,input)==1);assert(fwrite(&output,sizeof(output),1,expected)==1);
    }
    assert(fclose(input)==0&&fclose(expected)==0);return 0;
}
