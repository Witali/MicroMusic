// Public lifecycle and counter invariants, independent of compact field width.
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <fstream>
#include <iterator>
#include <vector>
#define private public
#include "Lpx4HybridCore.h"
#undef private
static uint64_t digest=UINT64_C(14695981039346656037);
static void word(uint32_t v){for(uint8_t i=0;i<4;i++){digest^=(uint8_t)v;digest*=UINT64_C(1099511628211);v>>=8;}}
static void status(const Lpx4HybridCore& d,bool ok){word(ok);word(d.samples());word(d.produced());word(d.sampleRate());word(d.error());word(d.finished());}
static void set32(uint8_t* b,uint32_t n){for(unsigned i=0;i<4;i++){b[i]=(uint8_t)n;n>>=8;}}
int main(int argc,char** argv){
 if(argc!=2)return 1;
 std::ifstream in(argv[1],std::ios::binary);
 std::vector<uint8_t> blob((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
 Lpx4HybridCore d;status(d,false);
 if(!d.begin(blob.data(),(uint16_t)blob.size()))return 2;
 const uint32_t total=d.samples();int16_t value;
 for(uint32_t n=0;n<total;n++){
  if(!d.nextS16(value)||d.produced()!=n+1||d.finished()!=(n+1==total))return 3;
  word((uint16_t)value);status(d,true);
 }
 if(d.nextS16(value)||d.error())return 4;
 status(d,false);
 const uint32_t counts[]={0,1,19,20,21,319,320,64000,64001,65535,65536,UINT32_MAX};
 for(unsigned c=0;c<sizeof(counts)/sizeof(counts[0]);c++){
  std::vector<uint8_t> bad=blob;set32(bad.data()+8,counts[c]);
  for(uint16_t size=0;size<=22;size++){
   status(d,d.begin(bad.data(),size));
   if(d.produced())return 5;
   Lpx4HybridCore copied=d,assigned;assigned=d;
   status(copied,copied.nextS16(value));status(assigned,assigned.nextS16(value));
   status(d,d.begin(0,0));if(d.produced()||d.finished())return 6;
  }
  status(d,d.begin(bad.data(),(uint16_t)bad.size()));
  if(d.produced())return 7;
  // Parse an error after valid begin; preserve successful-count semantics.
  if(!d.error()){
   d.bytes_=0;
#if !LPX4_ROM_POINTER
   d.cursor_=0;
#endif
   status(d,d.nextS16(value));
  }
  status(d,d.begin(0,0));if(d.produced())return 8;
  if(!d.begin(blob.data(),(uint16_t)blob.size()))return 9;
  for(unsigned n=0;n<21;n++)if(!d.nextS16(value))return 10;
  Lpx4HybridCore copy=d;d.begin(0,0);status(copy,true);
  if(!copy.nextS16(value)||copy.produced()!=22)return 11;
 }
 // Exhaust all legal total counts and every position in their final subframe.
 // DSP/packet execution is covered above; this isolates the public getter math.
 for(uint32_t count=1;count<=64000;count++){
  const uint32_t first=(count/20)*20;
  for(uint32_t produced=first;produced<=count;produced++){
   d.sampleCount_=count;d.error_=Lpx4HybridCore::NONE;
#if LPX4_BATCHED_REMAINING
   d.remaining_=count-first;d.subPos_=(uint8_t)(produced-first);
   d.subEnd_=(uint8_t)(count-first);
#else
   d.remaining_=count-produced;
#endif
   if(d.samples()!=count||d.produced()!=produced||d.finished()!=(produced==count))return 12;
   status(d,true);
  }
 }
 printf("%016llx\n",(unsigned long long)digest);
}
