/* Independent wide-product polynomial equations; no production Q14 helper. */
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "nb3_lsp_stage.h"
static uint32_t seed=0x1d87cb39;
static uint64_t cases,outputs;
static uint32_t random32(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static void input(int32_t p[6])
{
    p[0]=1048576;
    for(unsigned i=1;i<6;i++)p[i]=(int32_t)((random32()&0x3fffffff)^0x20000000)-0x20000000;
    p[1]=(int32_t)((uint32_t)p[1]&~63u);
}
static void check(const int32_t p[6],int16_t f,int stage)
{
    struct guarded {uint32_t before;int32_t value[6];uint32_t after;} a,b;
    int32_t expected[6];a.before=b.before=0x13572468;a.after=b.after=0x89abcdef;
    memcpy(a.value,p,24);memcpy(b.value,p,24);memcpy(expected,p,24);
    expected[stage+1]=(int32_t)(2*(int64_t)p[stage-1]-(((int64_t)f*p[stage])>>14));
    for(int j=stage;j>=2;j--)
        expected[j]=(int32_t)((int64_t)p[j]-(((int64_t)f*p[j-1])>>14)+p[j-2]);
    expected[1]=p[1]-(int32_t)f*64;
    if(stage==2)speex_nb3_lsp_stage2(a.value,f);
    else if(stage==3)speex_nb3_lsp_stage3(a.value,f);else speex_nb3_lsp_stage4(a.value,f);
    speex_nb3_lsp_stage_c(b.value,f,stage);
    assert(!memcmp(a.value,expected,24)&&!memcmp(b.value,expected,24));
    assert(a.before==0x13572468&&b.before==0x13572468&&a.after==0x89abcdef&&b.after==0x89abcdef);
    cases++;outputs+=stage+1;
}
int main(void)
{
    int32_t p[6];
    const int32_t bound[]={-536870912,-536870911,-73400331,-20971523,-6291457,-1,0,1,6291457,20971523,73400331,536870910,536870911};
    const int32_t aligned[]={-536870912,-8388608,-64,0,64,8388608,536870848};
    const int16_t fvalues[]={-32768,-32767,-16384,-1,0,1,16383,16384,32766,32767};
    for(int stage=2;stage<=4;stage++)for(int32_t f=-32768;f<=32767;f++){
        input(p);check(p,(int16_t)f,stage);
    }
    for(int stage=2;stage<=4;stage++)for(unsigned i=0;i<16384;i++){
        input(p);check(p,(int16_t)random32(),stage);
    }
    for(int stage=2;stage<=4;stage++)for(unsigned fi=0;fi<10;fi++)for(unsigned pi=0;pi<7;pi++)
        for(unsigned bi=0;bi<13;bi++)for(unsigned stride=0;stride<3;stride++){
            input(p);p[1]=aligned[pi];unsigned step=(unsigned[]){1,5,12}[stride];
            for(unsigned j=2;j<6;j++)p[j]=bound[(bi+j*step)%13];
            check(p,fvalues[fi],stage);
        }
    assert(cases==253950&&outputs==1015800);
    printf("{\"cases\":%"PRIu64",\"outputsPerPath\":%"PRIu64",\"all65536Signed16RootsPerStage\":true,"
        "\"signed30CoefficientLimits\":true,\"selectedAndForcedCExact\":true,"
        "\"independentSigned64ProductOracle\":true,\"guardsAndUntouchedWordsPreserved\":true}\n",cases,outputs);
    return 0;
}
