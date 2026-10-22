/* Offline-only LPC coefficient export, never compiled in firmware. */
#include <stdio.h>
#include <stdint.h>
#include <vector>
#include <fstream>
#include "../src/Lpx3AvrCore.h"
struct Input { std::vector<uint8_t> data; };
static uint8_t fetch(void* c,uint16_t off){return ((Input*)c)->data[off];}
int main(int argc,char**argv){
 if(argc!=3){fprintf(stderr,"usage: dump_lpc input.l3av output.s16le\n");return 2;}
 Input in;
 std::ifstream f(argv[1],std::ios::binary);
 in.data.assign(std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>());
 if(in.data.empty() || in.data.size()>65535)return 3;
 Lpx3AvrCore dec;
 if(!dec.begin(fetch,&in,(uint16_t)in.data.size()))return 4;
 FILE* o=fopen(argv[2],"wb");if(!o)return 5;
 uint8_t pcm=0;
 for(uint32_t i=0;i<dec.samples();i++){
   if(!dec.next(pcm)){fprintf(stderr,"decode error %u at %lu\n",dec.error(),(unsigned long)i);return 6;}
   if(i%20==0){int16_t coef[10];dec.copyCoefficients(coef);
     for(unsigned j=0;j<10;j++){
        uint16_t v=(uint16_t)coef[j]; fputc(v&255,o);fputc(v>>8,o);
     }
   }
 }
 fclose(o);return 0;
}
