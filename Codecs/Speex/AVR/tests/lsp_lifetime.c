/* Bounded interpolation and overlapping LPC output against untouched Xiph. */
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
static uint32_t seed=0x83b4d027,cases,calls;
static uint32_t random32(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static void quarters(const int16_t *old,const int16_t *next,unsigned count)
{
    int16_t raw[12],general[12],delta[12],out[12],plain[12],expected[12],a[10],b[10];
    unsigned i,sub;
    for(i=0;i<12;i++)raw[i]=general[i]=delta[i]=out[i]=plain[i]=expected[i]=0x1357;
    for(i=0;i<10;i++){
        assert(!(old[i]&15) && !(next[i]&15));
        a[i]=raw[i+1]=general[i+1]=old[i];b[i]=next[i];
        delta[i+1]=(next[i]>>2)-(old[i]>>2);
    }
    for(sub=0;sub<count;sub++){
        assert((int32_t)raw[1]+delta[1]>=16 && (int32_t)raw[10]+delta[10]<=25720);
        reference_interpolate(a,b,expected+1,10,sub,4,16);
        speex_nb3_interpolate(general+1,delta+1,plain+1);
        speex_nb3_interpolate_validated(raw+1,delta+1,out+1);
        assert(!memcmp(out+1,expected+1,20) && !memcmp(plain+1,expected+1,20));
        assert(!memcmp(raw,general,sizeof(raw)));
        for(i=0;i<10;i++){
            assert(raw[i+1]==old[i]+(int32_t)(sub+1)*((next[i]-old[i])/4));
            assert(delta[i+1]==((int32_t)next[i]-old[i])/4 && a[i]==old[i] && b[i]==next[i]);
        }
        for(i=0;i<12;i+=11)assert(raw[i]==0x1357 && general[i]==0x1357 && delta[i]==0x1357 &&
            out[i]==0x1357 && plain[i]==0x1357 && expected[i]==0x1357);
        calls++;
    }
    cases++;
}
int main(void)
{
    uint32_t n;unsigned i;int16_t previous[10];
    union {uint32_t align;char bytes[1024];} arena;
    int minRaw=32767,maxRaw=-32768;
    for(n=0;n<(1u<<18);n++){
        uint8_t packet[3]={(uint8_t)(n>>10),(uint8_t)(n>>2),(uint8_t)(n<<6)};
        int16_t next[10];SpeexBits bits={0};bits.chars=(char *)packet;bits.nbBits=18;
        reference_unquant(next,10,&bits);
        assert(bits.charPtr*8+bits.bitPtr==18 && !bits.overflow);
        for(i=0;i<10;i++){
            assert(next[i]>=96 && next[i]<=24880);
            if(next[i]<minRaw)minRaw=next[i];if(next[i]>maxRaw)maxRaw=next[i];
        }
        if(!n)memcpy(previous,next,sizeof(previous));
        quarters(previous,next,4);quarters(next,next,1);memcpy(previous,next,sizeof(previous));
    }
    for(n=0;n<65536;n++){
        int16_t a[10],b[10];
        for(i=0;i<10;i++){a[i]=(int16_t)(random32()&0xfff0);b[i]=(int16_t)(random32()&0xfff0);}
        a[0]=16+16*(random32()%1607);b[0]=16+16*(random32()%1607);
        a[9]=16+16*(random32()%1607);b[9]=16+16*(random32()%1607);
        quarters(a,b,4);
    }
    for(n=0;n<4;n++){
        int16_t a[10],b[10];
        for(i=0;i<10;i++){a[i]=(i&1)?32752:-32768;b[i]=(i&1)?-32768:32752;}
        a[0]=n&1?16:0;b[0]=n&1?16:64;a[9]=n&2?25712:25728;b[9]=n&2?25712:25696;
        quarters(a,b,4);
    }
    assert(cases==589828 && calls==1572880 && minRaw==96 && maxRaw==24880);
    for(n=0;n<240000;n++){
        int16_t input[12],expected[12],out[12],before[24],space[24];int offset;
        for(i=0;i<12;i++)input[i]=expected[i]=out[i]=0x2468;
        for(i=1;i<=10;i++)input[i]=n<160000?(int16_t)(random32()%25737):(int16_t)random32();
        if(n<80000)for(i=2;i<=10;i++){
            unsigned j=i;int16_t v=input[i];while(j>1 && input[j-1]>v){input[j]=input[j-1];j--;}input[j]=v;
        }
        reference_lsp(input+1,expected+1,10,arena.bytes);
        lsp_to_lpc(input+1,out+1,10,0);assert(!memcmp(out,expected,sizeof(out)));
        for(offset=-1;offset<=1;offset++){
            for(i=0;i<24;i++)space[i]=0x4b6d;
            memcpy(space+5,input+1,20);memcpy(before,space,sizeof(space));
            lsp_to_lpc(space+5,space+5+offset,10,0);
            assert(!memcmp(space+5+offset,expected+1,20));
            for(i=0;i<24;i++)if((int)i<5+offset || (int)i>=15+offset)assert(space[i]==before[i]);
        }
        assert(input[0]==0x2468 && input[11]==0x2468);
    }
    puts("PASS: 589828 bounded cases / 1572880 calls; all 262144 code triples, raw range 96..24880");
    puts("PASS: 240000 LPC inputs / 720000 overlapping outputs; exact untouched Xiph, guards preserved");
    return 0;
}
