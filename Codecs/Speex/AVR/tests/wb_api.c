#include "speex_wb1.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int16_t actual[320],first[320],second[320];
static unsigned used,calls;
static int cookie;
static void output(const int16_t *pcm,uint8_t count,void *context)
{
    assert(context==&cookie && count==80 && used+count<=320);
    memcpy(actual+used,pcm,count*2);used+=count;calls++;
}
static void decode(const uint8_t *p)
{used=calls=0;assert(!speex_wb1_decode(p,25,output,&cookie));assert(used==320&&calls==4);}
int main(int argc,char **argv)
{
    uint8_t packet[25],bad[25];unsigned i;
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f&&fread(packet,1,25,f)==25);fclose(f);
    speex_wb1_init();decode(packet);memcpy(first,actual,sizeof(first));
    decode(packet);memcpy(second,actual,sizeof(second));
    speex_wb1_init();decode(packet);assert(!memcmp(first,actual,sizeof(first)));
    used=calls=0;
    for(i=0;i<33;i++)if(i!=25)assert(speex_wb1_decode(packet,i,output,&cookie)==-1);
    assert(speex_wb1_decode(0,25,output,&cookie)==-1);
    assert(speex_wb1_decode(packet,25,0,&cookie)==-1);
    memcpy(bad,packet,25);bad[0]^=8;assert(speex_wb1_decode(bad,25,output,&cookie)==-1);
    memcpy(bad,packet,25);bad[20]^=16;assert(speex_wb1_decode(bad,25,output,&cookie)==-1);
    assert(!used&&!calls);decode(packet);assert(!memcmp(second,actual,sizeof(second)));
    speex_wb1_init();decode(packet);assert(!memcmp(first,actual,sizeof(first)));
    assert(speex_wb1_state_bytes()>0);
    puts("PASS: WB callback framing/context, invalid parameters/modes, unchanged state after rejection, reset");
}
