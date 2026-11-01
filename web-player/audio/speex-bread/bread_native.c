/* Host-only upstream fixed-point reference and project decoder harness.
 * Uses the repository's pinned Speex sources; no codec modifications. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef BREAD_PROJECT
#include "speex_nb.h"
#else
#include "speex/speex.h"
#include "speex/speex_bits.h"
#endif

static void sample(FILE *f,int16_t value){
    if(fputc((uint16_t)value&255,f)==EOF||fputc((uint16_t)value>>8,f)==EOF)exit(9);
}

int main(int argc,char **argv){
    if(argc!=6)return 2;
    if(strcmp(argv[1],"decode"))return 2;
    int mode=atoi(argv[2]);
    if(mode!=1&&mode!=3)return 2;
    unsigned width=mode==1?6:20;
    FILE *input=fopen(argv[3],"rb"),*output=fopen(argv[4],"wb");
    unsigned samples=(unsigned)strtoul(argv[5],0,10),frames=0;
    if(!input||!output||samples!=19200)return 3;
    int16_t pcm[160];unsigned char packet[200];
#ifdef BREAD_PROJECT
    speex_nb_init();
    for(;;){
        size_t n=fread(packet,1,width,input);if(!n)break;
        if(n!=width||packet[0]>>3!=mode||speex_nb_decode(packet,width,pcm))return 4;
        for(unsigned i=0;i<160;i++)sample(output,pcm[i]);
        frames++;
    }
    printf("{\"frames\":%u,\"decodedSamples\":%u,\"mode\":%d,\"packetBytes\":%u}",frames,frames*160,mode,width);
#else
    spx_int32_t off=0,decoder_lookahead=0,frame_size=0;
    void *decoder=speex_decoder_init(&speex_nb_mode);
    if(!decoder)return 4;
    speex_decoder_ctl(decoder,SPEEX_SET_ENH,&off);
    speex_decoder_ctl(decoder,SPEEX_SET_HIGHPASS,&off);
    speex_decoder_ctl(decoder,SPEEX_GET_LOOKAHEAD,&decoder_lookahead);
    speex_decoder_ctl(decoder,SPEEX_GET_FRAME_SIZE,&frame_size);
    if(frame_size!=160||decoder_lookahead<0)return 4;
    SpeexBits bits;speex_bits_init_buffer(&bits,packet,sizeof(packet));
    for(;;){
        size_t n=fread(packet,1,width,input);if(!n)break;
        if(n!=width||packet[0]>>3!=mode)return 5;
        speex_bits_set_bit_buffer(&bits,packet,width);
        if(speex_decode_int(decoder,&bits,pcm)||bits.overflow)return 6;
        for(unsigned i=0;i<160;i++)sample(output,pcm[i]);
        frames++;
    }
    printf("{\"frames\":%u,\"decodedSamples\":%u,\"mode\":%d,\"packetBytes\":%u,\"decoderLookahead\":%d}",
           frames,frames*160,mode,width,decoder_lookahead);
    speex_bits_destroy(&bits);speex_decoder_destroy(decoder);
#endif
    if(ferror(input)||fclose(output))return 8;
    fclose(input);return 0;
}
