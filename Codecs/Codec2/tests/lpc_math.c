#include "lpc_math.h"
#include "defines.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static uint32_t bits(float x){uint32_t b;memcpy(&b,&x,4);return b;}
static uint32_t seed=1;
static unsigned differences,maximum_ulp;
static FILE *patch;
static void check(float x){uint32_t a=bits(codec2_lpc_cosf(x)),b=bits(cosf(x));unsigned error=a>b?a-b:b-a;differences+=a!=b;maximum_ulp=error>maximum_ulp?error:maximum_ulp;if(patch&&a!=b){uint32_t pair[2]={bits(x),b};assert(fwrite(pair,sizeof(pair),1,patch)==1);}}
int main(int argc,char **argv){
    if(argc==2){patch=fopen(argv[1],"wb");assert(patch);}
    for(unsigned i=0;i<10;++i)assert(bits(codec2_lpc_initial_angle(i))==bits(i*PI/11));
    for(unsigned i=0;i<=392;++i){float a=(PI/4000.0)*(25.0f*i);assert(bits(a)==bits(codec2_lpc_grid_angle(i)));check(a);
        for(unsigned j=0;j<=392;++j){float b=(PI/4000.0)*(25.0f*j);check((float)(.5*a+.5*b));}
        for(unsigned j=0;j<10;++j){float initial=j*PI/11;check((float)(.5*initial+.5*a));}
    }
    unsigned reachable_differences=differences;
    if(patch){assert(!fclose(patch));patch=NULL;}
    for(unsigned i=0;i<1000000;++i){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);check((seed&0xffffff)/2097152.0f);}
    printf("{\"reachable_cosine_differences\":%u,\"total_differences\":%u,\"maximum_ulp\":%u,\"random_inputs\":1000000,\"grid_angles\":393,\"startup_angles\":10}\n",reachable_differences,differences,maximum_ulp);return 0;
}
