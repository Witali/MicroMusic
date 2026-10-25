/* Ten sequential outputs provide an independent model of paired C arithmetic. */
#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "nb3_lsp_finish.h"
static uint32_t seed=0x8fe1973a;
static uint64_t cases,positive_clips,negative_clips;
static uint32_t random32(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static void check(const uint32_t p[6],const uint32_t q[6])
{
    struct input {uint32_t before,value[6],after;} a,b;
    struct output {int16_t before,value[10],after;} c,d;
    uint32_t pp=0,pq=0;
    a.before=b.before=0x13572468;a.after=b.after=0x89abcdef;
    memcpy(a.value,p,24);memcpy(b.value,q,24);
    c.before=d.before=0x1357;c.after=d.after=0x2468;
    speex_nb3_lsp_finish10_c((const int32_t *)a.value,(const int32_t *)b.value,c.value);
    speex_nb3_lsp_finish10((const int32_t *)a.value,(const int32_t *)b.value,d.value);
    for(unsigned j=1;j<=10;j++){
        unsigned i=j<=5?j:10-j;
        uint32_t sum=p[i]+pp+q[i]-pq;
        int32_t expected=(int32_t)(sum+128)>>8;
        pp=p[i];pq=q[i];
        if(expected>32767){expected=32767;positive_clips++;}
        if(expected< -32767){expected=-32767;negative_clips++;}
        assert(c.value[j-1]==expected && d.value[j-1]==expected);
    }
    assert(!memcmp(a.value,p,24)&&!memcmp(b.value,q,24));
    assert(a.before==0x13572468&&b.before==0x13572468&&a.after==0x89abcdef&&b.after==0x89abcdef);
    assert(c.before==0x1357&&d.before==0x1357&&c.after==0x2468&&d.after==0x2468);
    cases++;
}
static void random_input(uint32_t p[6],uint32_t q[6])
{p[0]=q[0]=1048576;for(unsigned i=1;i<6;i++){p[i]=random32();q[i]=random32();}}
int main(void)
{
    uint32_t p[6],q[6];
    const uint32_t high[]={0,1,0x007ffe,0x007fff,0x008000,0x008001,0x7ffffe,0x7fffff,
        0x800000,0x800001,0xff7ffe,0xff7fff,0xff8000,0xff8001,0xff8002,0xfffffe,0xffffff};
    for(unsigned i=0;i<262144;i++){random_input(p,q);check(p,q);}
    for(unsigned h=0;h<sizeof(high)/sizeof(*high);h++)for(unsigned low=0;low<256;low++)
        for(unsigned j=1;j<=5;j++)for(unsigned mirror=0;mirror<2;mirror++){
            random_input(p,q);uint32_t target=(high[h]<<8)|low;
            p[j]=mirror?target-p[j-1]+q[j]-q[j-1]:target-p[j-1]-q[j]+q[j-1];
            check(p,q);
        }
    assert(cases==305664 && positive_clips && negative_clips);
    printf("{\"cases\":%"PRIu64",\"outputsPerPath\":%"PRIu64",\"selectedAndForcedCExact\":true,"
        "\"sequentialUnsigned32Oracle\":true,\"all256RoundingLowBytes\":true,"
        "\"positiveClips\":%"PRIu64",\"negativeClips\":%"PRIu64",\"guardsAndInputsPreserved\":true}\n",
        cases,10*cases,positive_clips,negative_clips);
    return 0;
}
