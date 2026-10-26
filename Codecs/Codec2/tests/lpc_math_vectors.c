#include "lpc_math.h"
#include "table_access.h"
#include "lpc_math_compat.inc"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void emit(FILE *input,FILE *expected,uint8_t mode,uint32_t word){
    float angle,result;memcpy(&angle,&word,4);result=mode==0?codec2_lpc_cosf(angle):mode==1?codec2_lpc_grid_angle((uint16_t)word):codec2_lpc_initial_angle(word);
    assert(fwrite(&mode,1,1,input)==1&&fwrite(&word,4,1,input)==1&&fwrite(&result,4,1,expected)==1);
}
int main(int argc,char **argv){
    assert(argc==3);FILE *input=fopen(argv[1],"wb"),*expected=fopen(argv[2],"wb");assert(input&&expected);uint32_t seed=1;
    for(unsigned i=0;i<4096;++i){
        uint32_t word;if(i<LPC_COSINE_COMPAT_COUNT)word=lpc_cosine_compat[2*i];else if(i==LPC_COSINE_COMPAT_COUNT)word=0;else{seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);float angle=(seed&0xffffff)/2097152.0f;if(i&1)angle=-angle;memcpy(&word,&angle,4);}emit(input,expected,0,word);
    }
    for(unsigned i=0;i<=392;++i)emit(input,expected,1,i);for(unsigned i=0;i<10;++i)emit(input,expected,2,i);
    assert(!fclose(input)&&!fclose(expected));return 0;
}
