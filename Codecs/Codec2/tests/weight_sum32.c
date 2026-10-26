#include "weight_sum32.h"
#include <limits.h>
#include <stdio.h>
static uint32_t seed=1;
static int32_t next(void){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);int32_t x;memcpy(&x,&seed,4);return x;}
static int64_t reference_half(int64_t x){return x<0?-((-x+1)/2):(x+1)/2;}
static void check(int32_t a,int32_t b){
    int64_t sum=(int64_t)a+b,difference=(int64_t)a-b,half=reference_half(difference);
    assert(weight_half_sum32(a,b)==reference_half(sum));
    if(half>=INT32_MIN&&half<=INT32_MAX)assert(weight_half_difference32(a,b)==half);
    if(sum>=INT32_MIN&&sum<=INT32_MAX)assert(weight_add32(a,b)==sum);
    if(difference>=INT32_MIN&&difference<=INT32_MAX)assert(weight_sub32(a,b)==difference);
}
int main(void){
    const int32_t edge[]={INT32_MIN,INT32_MIN+1,INT32_MIN+2,-65536,-32768,-2,-1,0,1,2,32767,65535,INT32_MAX-1,INT32_MAX};
    for(unsigned a=0;a<14;++a)for(unsigned b=0;b<14;++b)check(edge[a],edge[b]);
    for(unsigned i=0;i<1000000;++i){int32_t a=next(),b=next();check(a,b);}
    puts("PASS: 196 boundary and 1000000 random signed sums, differences and rounded half-sums match int64 C");return 0;
}
