#include "fixed_fifth.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static void word(FILE *f,uint32_t u){for(unsigned i=0;i<4;++i)assert(fputc((u>>(8*i))&255,f)!=EOF);}
int main(int argc,char **argv){
    assert(argc==4);FILE *input=fopen(argv[1],"wb"),*fixed=fopen(argv[2],"wb"),*reference=fopen(argv[3],"wb");assert(input&&fixed&&reference);
    const uint32_t edges[]={1,0x7fffff,0x800000,0x7f7fffff,0x80000000,0x7f800000};
    for(unsigned i=0;i<4096;++i){
        uint32_t u=((uint32_t)((i/16)%255)<<23)+((uint32_t)(i%16)*UINT32_C(0x7fffff)/15);
        if(i>=4090)u=edges[i-4090];float x;memcpy(&x,&u,4);word(input,u);
        float a=codec2_fixed_fifth(x),b=powf(x,.2f);memcpy(&u,&a,4);word(fixed,u);memcpy(&u,&b,4);word(reference,u);
    }
    assert(!fclose(input)&&!fclose(fixed)&&!fclose(reference));return 0;
}
