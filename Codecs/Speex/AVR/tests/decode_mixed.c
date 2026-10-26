/* Length-prefixed NB3/NB4 or WB packets; keep history across mode changes.
 * The reference build uses unmodified Xiph NB/HB and the independent compact
 * QMF oracle. Production rejects bad calls before EVERY valid frame, so a
 * comparison also detects unintended history/output changes on rejection. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef TEST_REFERENCE
#include "speex/speex.h"
#include "speex/speex_bits.h"
#else
#include "speex_nb.h"
#include "speex_wb1.h"
static int16_t pcm[320];
static unsigned used,calls;
static int cookie;
static void output(const int16_t *p,uint8_t n,void *ctx)
{
    assert(ctx==&cookie && n==80 && used+n<=320);
    memcpy(pcm+used,p,2*n);used+=n;calls++;
}
static int decode(int wb,const uint8_t *p,size_t n)
{return wb?speex_wb1_decode(p,n,output,&cookie):speex_nb_decode(p,n,pcm);}
static void reject(int wb,const uint8_t *packet,unsigned width)
{
    uint8_t bad[40];int16_t before[320];
    memcpy(before,pcm,sizeof(pcm));used=calls=0;
    for(unsigned n=0;n<=40;n++)if(n!=width)assert(decode(wb,packet,n)==-1);
    assert(decode(wb,0,width)==-1);
    if(wb)assert(speex_wb1_decode(packet,width,0,&cookie)==-1);
    else assert(speex_nb_decode(packet,width,0)==-1);
    memcpy(bad,packet,40);bad[0]^=8;assert(decode(wb,bad,width)==-1);
    if(wb) {
        memcpy(bad,packet,40);
        bad[width==25?20:27]^=width==25?16:1;
        assert(decode(wb,bad,width)==-1);
    }
    assert(!used && !calls && !memcmp(before,pcm,sizeof(pcm)));
}
#endif
int main(int argc,char **argv)
{
    assert(argc==4);int wb=atoi(argv[1]);assert(wb==0 || wb==1);
    FILE *in=fopen(argv[2],"rb"),*out=fopen(argv[3],"wb");assert(in && out);
    uint8_t packet[40];unsigned frames=0;int width;
#ifdef TEST_REFERENCE
    int16_t pcm[320];spx_int32_t off=0;SpeexBits bits;
    void *state=speex_decoder_init(speex_lib_get_mode(wb));assert(state);
    speex_decoder_ctl(state,SPEEX_SET_ENH,&off);
    speex_decoder_ctl(state,SPEEX_SET_HIGHPASS,&off);
    speex_bits_init_buffer(&bits,packet,sizeof(packet));
#else
    if(wb)speex_wb1_init();else speex_nb_init();
#endif
    while((width=fgetc(in))!=EOF) {
        assert(width==(wb?25:20) || width==(wb?32:28));
        memset(packet,0,sizeof(packet));assert(fread(packet,1,width,in)==(size_t)width);
#ifdef TEST_REFERENCE
        speex_bits_set_bit_buffer(&bits,packet,width);
        assert(!speex_decode_int(state,&bits,pcm) && !bits.overflow);
#else
        reject(wb,packet,(unsigned)width);
        assert(!decode(wb,packet,(unsigned)width));
        if(wb)assert(used==320 && calls==4);
#endif
        for(unsigned i=0;i<(wb?320u:160u);i++) {
            assert(fputc((uint16_t)pcm[i]&255,out)!=EOF);
            assert(fputc((uint16_t)pcm[i]>>8,out)!=EOF);
        }
        frames++;
    }
    assert(frames && !ferror(in));assert(!fclose(out));fclose(in);
#ifdef TEST_REFERENCE
    speex_bits_destroy(&bits);speex_decoder_destroy(state);
#endif
    return 0;
}
