#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "speex_nb8.h"
static uint32_t seed=0x52ABCDEFu;
static uint32_t rng(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
int main(void) {
 SpeexNB8 s; int16_t pcm[160]; uint8_t frame[20];
 speex_nb8_init(&s);
 unsigned long sample_count=0,valid=0;
 for(int t=0;t<12000;t++){
   if(t%47==0)speex_nb8_init(&s);
   for(unsigned k=0;k<20;k++)frame[k]=rng()&255;
   frame[0]=(frame[0]&0x07)|0x18;
   if(speex_nb8_decode(&s,frame,pcm)){printf("unexpected invalid mode t=%d\n",t);return 7;}
   valid++;sample_count+=160;
 }
 /* Guard unsupported modes: do not modify state */
 for(unsigned b=0;b<256;b++){
   memset(frame,0,20);frame[0]=(uint8_t)b;
   if((b&0xf8)==0x18)continue;
   SpeexNB8 saved=s;
   int ret=speex_nb8_decode(&s,frame,pcm);
   if(ret>=0 || memcmp(&saved,&s,sizeof s)){printf("bad reject frame 0x%02x ret=%d\n",b,ret);return 8;}
 }
 printf("PASS decoded %lu synthetic mode3 frames (%lu samples); rejected all other prefixes\n",valid,sample_count);
 return 0;
}
