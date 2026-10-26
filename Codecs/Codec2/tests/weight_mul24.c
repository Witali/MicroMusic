#include "weight_mul24.h"
#include <assert.h>
#include <stdio.h>
static uint32_t seed=1;
static int32_t sample(void){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);return (int32_t)(seed&0xffffff)-8388608;}
static int32_t reference(int64_t value,unsigned bits){int64_t half=INT64_C(1)<<(bits-1);return (int32_t)(value<0?-((-value+half)>>bits):(value+half)>>bits);}
static void check(int32_t a,int32_t b,int32_t c,int32_t d){
    for(unsigned q=14;q<=22;q+=8){
        int32_t limit=INT32_C(1)<<q,wb=b<-limit?-limit:b>limit?limit:b,wd=d<-limit?-limit:d>limit?limit:d;
        assert(weight_round48(weight_sub48(weight_product24(a,wb),weight_product24(c,wd)),q)==reference((int64_t)a*wb-(int64_t)c*wd,q));
        assert(weight_round48(weight_add48(weight_product24(a,wb),weight_product24(c,wd)),q)==reference((int64_t)a*wb+(int64_t)c*wd,q));
    }
}
int main(void){
    const int32_t edge[]={-8388608,-8388607,-65536,-32768,-1,0,1,32767,65535,8388607};
    for(unsigned a=0;a<10;++a)for(unsigned b=0;b<10;++b)for(unsigned c=0;c<10;++c)for(unsigned d=0;d<10;++d)check(edge[a],edge[b],edge[c],edge[d]);
    for(unsigned i=0;i<1000000;++i)check(sample(),sample(),sample(),sample());
    puts("PASS: 10000 boundary and 1000000 random complex products/roundings match int64");return 0;
}
