#include "../src/Lpx3AvrCore.h"
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <cstring>
static uint8_t readROM(void* d,uint16_t p){return ((std::vector<uint8_t>*)d)->at(p);}
struct Ring {
  uint8_t data[512]{};
  unsigned head=0,tail=0;
  size_t lost=0;
  unsigned fill()const{return (head-tail)&511;}
  bool add(uint8_t v){if(((head+1)&511)==tail)return false;data[head]=v;head=(head+1)&511;return true;}
  int next(){if(tail==head){++lost;return -1;}int x=data[tail];tail=(tail+1)&511;return x;}
};
int main(int argc,char** argv){
 if(argc!=2){fprintf(stderr,"test_buffer clip.l3av\n");return 2;}
 std::ifstream f(argv[1],std::ios::binary);std::vector<uint8_t> b((std::istreambuf_iterator<char>(f)),{});
 Lpx3AvrCore reference,live;
 if(!reference.begin(readROM,&b,b.size())||!live.begin(readROM,&b,b.size()))return 3;
 std::vector<uint8_t> samples;uint8_t s;
 while(reference.next(s))samples.push_back(s);
 Ring r;
 while(r.fill()<384 && live.next(s))r.add(s); // startup: 48ms at 8kHz
 size_t readSamples=0;int credit=0;
 for(size_t tick=0;tick<samples.size();tick++){
  // 10,000 samples/s producer budget vs 8,000 sample/s consumer.
  // Each 0.5sec, simulate a non-preemptive 20 ms foreground stall.
  const size_t within=tick%4000;
  if(!(within>=1900 && within<2060)){
    credit+=5;int allowed=credit/4;credit%=4;
    while(allowed-->0 && r.fill()<480 && live.next(s))r.add(s);
  }
  const int got=r.next();if(got<0){fprintf(stderr,"UNDERRUN at sample %zu\n",tick);return 4;}
  if(got!=(int)samples[tick]){
   fprintf(stderr,"PCM CORRUPTION @%zu original=%d queued=%d\n",tick,samples[tick],got);return 5;
  }
  ++readSamples;
 }
 printf("PASS BUFFER: %zu samples; 8kHz, startup 384 B, ring 512 B, +25%% producer throughput, 20ms stalls/0.5s, underruns=%zu\n",readSamples,r.lost);
 return 0;
}
