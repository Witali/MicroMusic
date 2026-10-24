/* Standalone host decoder: input is Speex NB 8kbps 20-byte raw frames,
 * output a WAV 8kHz mono 16-bit. This is not an Ogg demuxer.
 */
#include "speex_nb8.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
static void le16(FILE *f, uint16_t v) { fputc(v&255,f);fputc(v>>8,f); }
static void le32(FILE *f, uint32_t v) { le16(f,(uint16_t)v); le16(f,(uint16_t)(v>>16)); }
int main(int argc,char **argv) {
    if(argc!=3) {fprintf(stderr,"Usage: %s input.spxraw output.wav\n",argv[0]);return 2;}
    FILE *in=fopen(argv[1],"rb"); if(!in) {perror(argv[1]);return 2;}
    if(fseek(in,0,SEEK_END)) return 2;
    long len=ftell(in);
    if(len<0||len%20) {fputs("Raw input size must be multiple of 20\n",stderr);return 2;}
    rewind(in);
    FILE *out=fopen(argv[2],"wb");if(!out) {perror(argv[2]);return 2;}
    uint32_t samples=(uint32_t)(len/20)*160;
    fwrite("RIFF",1,4,out);le32(out,36+2*samples);
    fwrite("WAVEfmt ",1,8,out);le32(out,16);le16(out,1);le16(out,1);le32(out,8000);
    le32(out,16000);le16(out,2);le16(out,16);
    fwrite("data",1,4,out);le32(out,2*samples);
    SpeexNB8 *dec=(SpeexNB8*)calloc(1,sizeof(SpeexNB8));
    if(!dec) return 2;
    uint8_t packet[20];int16_t pcm[160];speex_nb8_init(dec);
    for(long i=0;i<len/20;i++) {
        if(fread(packet,1,20,in)!=20) return 3;
        if(speex_nb8_decode(dec,packet,pcm)) {fprintf(stderr,"Unsupported Speex mode at frame %ld\n",i);return 4;}
        for(unsigned n=0;n<160;n++) le16(out,(uint16_t)pcm[n]);
    }
    fprintf(stderr,"decoded %ld frames (%.2f sec); state %zu bytes (host), 8kHz mono\n",len/20,(double)(len/20)/50,sizeof(SpeexNB8));
    fclose(in);fclose(out);free(dec);return 0;
}
