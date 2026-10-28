// Compiled bounded Rice interface/state equivalence against the old reader.
#include <stdint.h>
#include <stdio.h>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
#ifndef RICE_INTERFACE
#define RICE_INTERFACE 0
#endif
static uint8_t referenceRice(Lpx4HybridCore& d,uint8_t k,uint8_t width){
 uint8_t high=0;
 while(high<8 && !d.readOne()){
  if(d.error_)return 0;
  ++high;
 }
 if(high==8)return d.readBits(width);
 return (high<<k)|(k?d.readBits(k):0);
}
static void setup(Lpx4HybridCore& d,const uint8_t* bytes,uint8_t size,uint8_t cache,uint8_t available,uint8_t error){
 d.data_=bytes;d.bytes_=size;d.bitBuffer_=cache;d.bitsLeft_=available;d.error_=(Lpx4HybridCore::Error)error;
#if !LPX4_ROM_POINTER
 d.cursor_=0;
#endif
#ifdef LPX3_COST_INSTRUMENT
 d.bitCalls_=d.romByteCalls_=0;
#endif
}
int main(){
 const uint8_t ks[4]={1,0,2,1},widths[4]={5,6,6,7};
 const uint8_t errors[3]={Lpx4HybridCore::NONE,Lpx4HybridCore::END_OF_ROM,Lpx4HybridCore::BAD_HEADER};
 Lpx4HybridCore actual,reference;uint32_t cases=0;
 for(uint8_t available=0;available<=8;available++)for(uint16_t cached=0;cached<(1U<<available);cached++)
 for(uint16_t next=0;next<256;next++)for(uint8_t length=0;length<=2;length++)for(uint8_t second=0;second<2;second++)
 for(uint8_t shape=0;shape<4;shape++)for(uint8_t error=0;error<3;error++){
  const uint8_t bytes[2]={(uint8_t)next,(uint8_t)(second?~next:0)};
  setup(actual,bytes,length,cached,available,errors[error]);setup(reference,bytes,length,cached,available,errors[error]);
  const uint8_t expected=referenceRice(reference,ks[shape],widths[shape]);uint8_t value=0;bool ok;
#if RICE_INTERFACE==1
  const int8_t tagged=actual.readSpeechRice(ks[shape],widths[shape]);ok=tagged>=0;value=(uint8_t)tagged;
#elif RICE_INTERFACE==2
  ok=actual.readSpeechRice(ks[shape],widths[shape],value);
#elif RICE_INTERFACE==3
  value=actual.readSpeechRice((widths[shape]<<2)|ks[shape]);ok=!actual.error_;
#else
  value=actual.readSpeechRice(ks[shape],widths[shape]);ok=!actual.error_;
#endif
  if(ok!=!reference.error_ || (ok && value!=expected))return 1;
  if(actual.error_!=reference.error_ || actual.data_!=reference.data_ || actual.bytes_!=reference.bytes_ ||
     actual.bitBuffer_!=reference.bitBuffer_ || actual.bitsLeft_!=reference.bitsLeft_)return 2;
#if !LPX4_ROM_POINTER
  if(actual.cursor_!=reference.cursor_)return 3;
#endif
#ifdef LPX3_COST_INSTRUMENT
  if(actual.bitCalls_!=reference.bitCalls_ || actual.romByteCalls_!=reference.romByteCalls_)return 4;
#endif
  ++cases;
 }
 printf("%lu Rice interface states exact\n",(unsigned long)cases);
}
