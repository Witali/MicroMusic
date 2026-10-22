#include "../src/Lpx3AvrCore.h"
#include <cstdio>
#include <cstdlib>
#include <vector>
#include <cstdint>
#include <fstream>
#include <iterator>
#include <cstring>
static uint8_t readByte(void* ctx,uint16_t pos){return (*(const std::vector<uint8_t>*)ctx)[pos];}
int main(int argc,char** argv){
 if(argc!=3){fprintf(stderr,"usage: decode_host source.l3av output.pcm8\n");return 2;}
 std::ifstream file(argv[1],std::ios::binary);std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)),{});
 Lpx3AvrCore d;
 if(!d.begin(readByte,&data,(uint16_t)data.size())){
  fprintf(stderr,"decoder rejected header %d\n",int(d.error()));return 3;
 }
 std::vector<uint8_t> samples; samples.reserve(d.samples());
 uint8_t v;
 while(d.next(v))samples.push_back(v);
 if(d.error()!=Lpx3AvrCore::NONE||samples.size()!=d.samples()){
  fprintf(stderr,"decoder error=%d produced=%zu expected=%lu\n",int(d.error()),samples.size(),(unsigned long)d.samples());return 4;
 }
 std::ofstream o(argv[2],std::ios::binary);o.write((const char*)samples.data(),samples.size());
 if(!o)return 5;
 printf("PASS samples=%zu bytes=%zu sr=%u\n",samples.size(),data.size(),d.sampleRate());
#ifdef LPX3_COST_INSTRUMENT
 printf("COUNTERS bit_calls=%lu byte_calls=%lu lsf=%lu\n",(unsigned long)d.bitCalls(),(unsigned long)d.romByteCalls(),(unsigned long)d.lsfConverts());
#endif
 return 0;
}
