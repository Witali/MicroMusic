#include "speex_wb1.h"
#ifdef __AVR__
#ifndef SPEEX_TEST_PACKET_BYTES
#define SPEEX_TEST_PACKET_BYTES 25
#endif
uint8_t speex_test_packet[SPEEX_TEST_PACKET_BYTES];
volatile uint8_t speex_test_command,speex_test_status,speex_test_chunks;
volatile int8_t speex_test_result;
const int16_t * volatile speex_test_pcm;
static void output(const int16_t *pcm,uint8_t n,void *context)
{(void)n;(void)context;speex_test_pcm=pcm;++speex_test_chunks;}
int main(void)
{
    speex_wb1_init();speex_test_status=1;
    for(;;) {
        if(speex_test_command==1) {
            speex_test_result=speex_wb1_decode(speex_test_packet,SPEEX_TEST_PACKET_BYTES,output,0);
            speex_test_command=0;speex_test_status=2;
        }else if(speex_test_command==2) {
            speex_wb1_init();speex_test_command=0;speex_test_status=1;
        }
    }
}
#else
#include <stdio.h>
#include <stdlib.h>
static void output(const int16_t *pcm,uint8_t n,void *context)
{FILE *f=context;for(unsigned i=0;i<n;i++){fputc((uint16_t)pcm[i]&255,f);fputc((uint16_t)pcm[i]>>8,f);}}
int main(int argc,char **argv)
{
    uint8_t packet[32];size_t count,bytes=argc==4?(size_t)atoi(argv[3]):25;
    if((argc!=3 && argc!=4) || (bytes!=25 && bytes!=32))return 2;
    FILE *in=fopen(argv[1],"rb"),*out=fopen(argv[2],"wb");if(!in||!out)return 3;
    speex_wb1_init();
    while((count=fread(packet,1,bytes,in)))if(count!=bytes||speex_wb1_decode(packet,bytes,output,out))return 4;
    return fclose(out)!=0;
}
#endif
