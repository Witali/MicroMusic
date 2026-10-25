/* Independent signed64 sum/product equations for the two-root constructor. */
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "nb3_lsp_first.h"
static uint32_t seed=0x713a6c91;
static uint64_t cases;
static uint32_t random32(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static void check(int16_t a,int16_t b)
{
    struct guarded {uint32_t before;int32_t value[3];uint32_t after;} p,q;
    p.before=q.before=0x13572468;p.after=q.after=0x89abcdef;
    int32_t salt=(int32_t)random32();
    p.value[0]=q.value[0]=salt;p.value[1]=q.value[1]=0x12345678;p.value[2]=q.value[2]=0x76543210;
    int32_t first=(int32_t)(-((int64_t)a+b)*64);
    int32_t second=2097152+(int32_t)(((int64_t)a*b+255)>>8);
    speex_nb3_lsp_first(p.value,a,b);speex_nb3_lsp_first_c(q.value,a,b);
    assert(p.value[1]==first&&q.value[1]==first&&p.value[2]==second&&q.value[2]==second);
    assert(p.value[0]==salt&&q.value[0]==salt);
    assert(p.before==0x13572468&&q.before==0x13572468&&p.after==0x89abcdef&&q.after==0x89abcdef);
    cases++;
}
int main(void)
{
    const int16_t fixed[]={-32768,-32767,-32512,-256,-255,-129,-128,-1,0,1,127,128,255,256,32766,32767};
    for(unsigned j=0;j<16;j++)for(int32_t a=-32768;a<=32767;a++)check((int16_t)a,fixed[j]);
    for(unsigned ah=0;ah<256;ah++)for(unsigned bh=0;bh<256;bh++)for(unsigned carry=0;carry<2;carry++)
        check((int16_t)((ah<<8)|(carry?255:0)),(int16_t)((bh<<8)|(carry?1:0)));
    for(int32_t sum=-65536;sum<=65534;sum++){
        int32_t a=sum< -32768?-32768:sum>32767?32767:sum;check((int16_t)a,(int16_t)(sum-a));
    }
    for(unsigned j=0;j<65536;j++)check((int16_t)random32(),(int16_t)random32());
    assert(cases==1376255);
    printf("{\"cases\":%"PRIu64",\"outputWordsPerPath\":%"PRIu64",\"selectedAndForcedCExact\":true,"
        "\"independentSigned64Oracle\":true,\"allSigned16LeftRootsAt16RightRoots\":true,"
        "\"allSigned17Sums\":true,\"all131072HighByteCarryInputs\":true,\"guardsAndP0Preserved\":true}\n",cases,2*cases);
    return 0;
}
