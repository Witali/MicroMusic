/* Every 18-bit LSP / 5-bit gain combination against untouched Xiph code. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "nb3_lsp.h"
#include "lsp.h"
#include "speex/speex_bits.h"
void reference_lsp_unquant_lbr(spx_lsp_t *,int,SpeexBits *);
unsigned reference_bits_unpack_unsigned(SpeexBits *,int);

static void field(uint8_t *p,unsigned *bit,unsigned width,uint32_t value)
{
    while(width--) {
        const unsigned mask=1u<<(7-(*bit&7));
        p[*bit>>3]=(p[*bit>>3]&~mask)|(((value>>width)&1)?mask:0);
        ++*bit;
    }
}
int main(void)
{
    uint32_t code,cases=0;
    unsigned gain,i;
    int minimum=32767,maximum=-32768;
    for(code=0;code<(1u<<18);code++)for(gain=0;gain<32;gain++) {
        uint8_t packet[22],saved[22];
        int16_t out[12],expected[12];
        unsigned bit=0;
        SpeexBits bits={0};
        memset(packet,0x69,sizeof(packet));
        field(packet+1,&bit,5,3);field(packet+1,&bit,18,code);field(packet+1,&bit,5,gain);
        memcpy(saved,packet,sizeof(packet));
        out[0]=expected[0]=0x1357;out[11]=expected[11]=0x2468;
        bits.chars=(char *)packet+1;bits.nbBits=160;bits.bitPtr=5;bits.buf_size=20;
        reference_lsp_unquant_lbr(expected+1,10,&bits);
        assert(bits.charPtr*8+bits.bitPtr==23);
        const unsigned reference_gain=reference_bits_unpack_unsigned(&bits,5);
        speex_nb3_lsp_quarters(packet+1,out+1);
        assert(speex_nb3_frame_gain(packet+1)==reference_gain && reference_gain==gain);
        assert(bits.charPtr*8+bits.bitPtr==28 && !bits.overflow);
        for(i=1;i<=10;i++) {
            assert(!(expected[i]&15) && 4*out[i]==expected[i]);
            assert(out[i]>=-1024 && out[i]<=6644);
            if(expected[i]<minimum)minimum=expected[i];
            if(expected[i]>maximum)maximum=expected[i];
        }
        assert(!memcmp(packet,saved,sizeof(packet)));
        assert(out[0]==0x1357 && expected[0]==0x1357 && out[11]==0x2468 && expected[11]==0x2468);
        cases++;
    }
    assert(cases==8388608);
    printf("PASS: %lu complete LSP/gain combinations; untouched Xiph raw angles and gain exact; raw range %d..%d\n",
        (unsigned long)cases,minimum,maximum);
    return 0;
}
