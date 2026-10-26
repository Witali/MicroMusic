#include "weight_round.h"
#include <assert.h>
#include <stdio.h>
static uint32_t seed=1;
static uint32_t next(void){seed=seed*UINT32_C(1664525)+UINT32_C(1013904223);return seed;}
static void check(int64_t v,unsigned q){int64_t h=INT64_C(1)<<(q-1);int32_t expected=(int32_t)(v<0?-((-v+h)>>q):(v+h)>>q);assert(weight_round64(v,q)==expected);}
int main(void){
    for(unsigned q=1;q<=30;++q){int64_t h=INT64_C(1)<<(q-1);for(int d=-2;d<=2;++d){check(h+d,q);check(-h+d,q);check(d,q);}}
    for(unsigned i=0;i<1000000;++i){unsigned q=1+next()%30;int32_t whole=(int32_t)(next()&0x7fffffff)-1073741824;uint32_t fraction=next()&((UINT32_C(1)<<q)-1);check((int64_t)whole*(INT64_C(1)<<q)+fraction,q);}
    puts("PASS: signed half-step boundaries and 1000000 random int64 roundings match nonnegative-magnitude reference");return 0;
}
