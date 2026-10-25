/* Real codebook quarters: original interpolation/LPC vs both production paths. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "nb3_interpolate.h"
#include "lsp.h"
#include "speex/speex_bits.h"
void reference_lsp(const spx_lsp_t *,spx_coef_t *,int,char *);
void reference_interpolate(spx_lsp_t *,spx_lsp_t *,spx_lsp_t *,int,int,int,spx_word16_t);
void reference_unquant(spx_lsp_t *,int,SpeexBits *);
typedef struct {int16_t before,v[10],after;} guarded;
static uint32_t seed=0x1973a44d,cases,calls,masks[4],fineRepairs;
static uint32_t random32(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static void endpoint(uint32_t code,int16_t *out)
{
    uint8_t p[3]={(uint8_t)(code>>10),(uint8_t)(code>>2),(uint8_t)(code<<6)};
    SpeexBits bits={0};bits.chars=(char *)p;bits.nbBits=18;bits.buf_size=3;
    reference_unquant(out,10,&bits);assert(bits.charPtr*8+bits.bitPtr==18 && !bits.overflow);
}
static void check(const int16_t *old,const int16_t *next,unsigned count)
{
    guarded a,b,rawF,rawS,delta,angles,expectedAngles,coefF,coefS,expected;
    guarded *all[]={&a,&b,&rawF,&rawS,&delta,&angles,&expectedAngles,&coefF,&coefS,&expected};
    union {uint32_t align;unsigned char bytes[1032];} arena;
    unsigned i,sub,j;
    memset(arena.bytes,0x69,sizeof(arena.bytes));
    for(i=0;i<sizeof(all)/sizeof(all[0]);i++){all[i]->before=0x1357;all[i]->after=0x2468;}
    for(i=0;i<10;i++){
        assert(!(old[i]&15) && !(next[i]&15));
        a.v[i]=rawF.v[i]=rawS.v[i]=old[i];b.v[i]=next[i];delta.v[i]=(next[i]>>2)-(old[i]>>2);
    }
    for(sub=0;sub<count;sub++){
        reference_interpolate(a.v,b.v,expectedAngles.v,10,sub,4,16);
        reference_lsp(expectedAngles.v,expected.v,10,(char *)arena.bytes+4);
        speex_nb3_interpolate_codebook(rawS.v,delta.v,angles.v);
        memcpy(coefS.v,angles.v,20);lsp_to_lpc(coefS.v,coefS.v,10,0);
        speex_nb3_interpolate_lpc(rawF.v,delta.v,coefF.v);
        assert(!memcmp(angles.v,expectedAngles.v,20));
        assert(!memcmp(coefS.v,expected.v,20) && !memcmp(coefF.v,expected.v,20));
        for(i=0;i<10;i++){
            int32_t step=((int32_t)next[i]-old[i])/4;
            assert(rawF.v[i]==old[i]+(int32_t)(sub+1)*step && rawF.v[i]==rawS.v[i]);
            assert(!(rawF.v[i]&3) && !(expectedAngles.v[i]&1));
            assert(delta.v[i]==step && a.v[i]==old[i] && b.v[i]==next[i]);
            if(i!=3 && i!=4 && i!=5)assert(angles.v[i]==rawF.v[i]);
        }
        unsigned mask=(expectedAngles.v[3]!=rawF.v[3])|((expectedAngles.v[5]!=rawF.v[5])<<1);
        assert(mask!=3);masks[mask]++;
        if((expectedAngles.v[3]&3)||(expectedAngles.v[4]&3))fineRepairs++;
        for(j=0;j<sizeof(all)/sizeof(all[0]);j++)assert(all[j]->before==0x1357 && all[j]->after==0x2468);
        for(i=0;i<4;i++)assert(arena.bytes[i]==0x69 && arena.bytes[1028+i]==0x69);
        calls++;
    }
    cases++;
}
int main(void)
{
    uint32_t code;int16_t old[10],next[10];
    for(code=0;code<(1u<<18);code++){
        endpoint(code,next);endpoint(random32()&0x3ffff,old);
        check(old,next,4);check(next,next,1);
    }
    assert(cases==524288 && calls==1310720 && masks[0] && masks[1] && masks[2] && !masks[3] && fineRepairs);
    printf("{\"cases\":524288,\"calls\":1310720,\"all262144CodeTriples\":true,"
        "\"fusedAndSeparateExactAgainstUntouchedXiph\":true,\"rawStateExact\":true,"
        "\"guardsAndInputsPreserved\":true,\"repairMasks\":[%lu,%lu,%lu,0],\"fineStepRepairs\":%lu}\n",
        (unsigned long)masks[0],(unsigned long)masks[1],(unsigned long)masks[2],(unsigned long)fineRepairs);
    return 0;
}
