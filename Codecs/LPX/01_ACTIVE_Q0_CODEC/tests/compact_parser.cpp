// Frozen-baseline parser trace: public header metadata and bounded v5 fields.
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
static uint64_t digest=UINT64_C(14695981039346656037);
static uint32_t cases;
static void word(uint32_t value){
 for(uint8_t i=0;i<4;i++){digest^=(uint8_t)value;digest*=UINT64_C(1099511628211);value>>=8;}
}
// Detect the reference common/old-compact member without coupling the trace
// to the current private flag representation.
template<class T> static auto extrasImpl(const T& d,int)->decltype(d.speechCompact_){return d.speechCompact_&128;}
template<class T> static uint8_t extrasImpl(const T& d,long){return d.speechProfile_&128;}
static uint8_t extras(const Lpx4HybridCore& d){return extrasImpl(d,0);}
template<class T> static auto flagsImpl(T& d,uint8_t value,int)->decltype(d.speechCompact_=value,void()){
 d.speechProfile_=value&127;d.speechCompact_=1|(value&128);
}
template<class T> static void flagsImpl(T& d,uint8_t value,long){d.speechProfile_=value;}
static void flags(Lpx4HybridCore& d,uint8_t value){flagsImpl(d,value,0);}
// Trace semantic centered values, independently of compact private storage.
static uint16_t lsf(const Lpx4HybridCore& d,uint16_t stored){
 if(sizeof(d.cur_[0])!=1)return stored;
 return stored ? (uint16_t)((stored*2-1)<<((d.speechProfile_&2)?3:4)) : 0;
}
template<class T> static auto halfImpl(const T& d,int)->decltype(d.speechHalf_){return d.speechHalf_;}
template<class T> static uint8_t halfImpl(const T& d,long){return (d.subIndex_>>3)&1;}
static void snapshot(const Lpx4HybridCore& d,bool accepted){
 ++cases;word(accepted);word(d.samples());word(d.produced());word(d.sampleRate());word(d.error());word(d.finished());
#if LPX4_ROM_POINTER
 word(d.bytes_);
#else
 word(d.bytes_-d.cursor_);
#endif
 word(d.bitBuffer_);word(d.bitsLeft_);word(d.speechProfile_&127);word(extras(d));
 word(halfImpl(d,0));word(d.initializedFrame_);word(d.staticSpectrum_);word(d.blockStep_);word(d.lag_);word(d.gain_);
 for(uint8_t i=0;i<10;i++){word(lsf(d,d.prev_[i]));word(lsf(d,d.cur_[i]));}
#ifdef LPX3_COST_INSTRUMENT
 word(d.bitCalls_);word(d.romByteCalls_);word(d.lsfConverts_);
#endif
 word(d.pulseCount_);word(d.pulseIndex_);
 for(uint8_t i=0;i<d.pulseCount_;i++){word(d.pulsePos_[i]);word((uint8_t)d.pulseAmp_[i]);}
}
static void put16(uint8_t* b,uint16_t value){b[0]=(uint8_t)value;b[1]=(uint8_t)(value>>8);}
static void put32(uint8_t* b,uint32_t value){put16(b,(uint16_t)value);put16(b+2,(uint16_t)(value>>16));}
struct Writer {
 uint8_t data[128];uint16_t bits;
 Writer():bits(0){memset(data,0,sizeof(data));}
 void put(uint8_t value,uint8_t width){for(uint8_t i=0;i<width;i++,bits++)data[bits>>3]|=((value>>i)&1)<<(bits&7);}
 void rice(uint8_t value,uint8_t k,uint8_t width){
  uint8_t q=value>>k;
  if(q>=8){put(0,8);put(value,width);}
  else{put(0,q);put(1,1);put(value&((1u<<k)-1),k);}
 }
 uint16_t size()const{return (bits+7)>>3;}
};
static void setup(Lpx4HybridCore& d,const Writer& w,uint16_t size,uint8_t format){
 d.resetState();d.data_=w.data;d.bytes_=size;
#if !LPX4_ROM_POINTER
 d.cursor_=0;
#endif
 flags(d,format);memset(d.pulsePos_,0,sizeof(d.pulsePos_));memset(d.pulseAmp_,0,sizeof(d.pulseAmp_));
}
static void frame(Lpx4HybridCore& d,uint8_t profile,bool delta,uint8_t old,int16_t last,uint8_t code,uint32_t serial){
 const uint8_t bits=profile==4?5:6,k=bits-4-delta,shift=10-bits;
 Writer w;w.put(1,1);w.put(delta,1);
 for(uint8_t i=0;i<10;i++){
  uint8_t z=0;
  if(i==0 && last>=0){int16_t diff=last-old;z=delta?(diff<0?-2*diff-1:2*diff):last;}
  else if((last<0 && i==0)||(last>=0 && i==1))z=code;
  w.rice(z,k,bits+delta);
 }
 w.put(20,5);w.put(0,7);w.put(2,3);
 const uint16_t sizes[4]={w.size(),0,1,(uint16_t)(w.size()-1)};
 const uint8_t trials=serial%257==0?4:1;
 for(uint8_t j=0;j<trials;j++){
  setup(d,w,sizes[j],profile);d.initializedFrame_=true;
  for(uint8_t i=0;i<10;i++)d.cur_[i]=sizeof(d.cur_[0])==1 ? old+1 : (old<<shift)+(1u<<(shift-1));
  snapshot(d,d.readFrame());
 }
}
int main(){
 Lpx4HybridCore d;
 static uint8_t header[65535];memcpy(header,"L4HY",4);header[4]=5;header[5]=4;
 put16(header+6,8000);put32(header+8,320);put16(header+12,13926);put16(header+16,320);put16(header+18,160);
 const uint16_t payloads[9]={0,1,20,21,22,65512,65513,65514,65535};
 for(uint32_t size=0;size<=65535;size++)for(uint8_t p=0;p<9;p++){
  put16(header+20,payloads[p]);snapshot(d,d.begin(header,(uint16_t)size));
  if(((size+payloads[p])&127)==0)snapshot(d,d.begin(0,0));
 }
 const uint16_t sizes[4]={20,21,22,65535};
 for(uint8_t i=0;i<4;i++)for(uint32_t payload=0;payload<=65535;payload++){
  put16(header+20,(uint16_t)payload);snapshot(d,d.begin(header,sizes[i]));
 }
 const uint32_t samples[9]={0,1,19,20,64000,64001,65535,65536,UINT32_MAX};put16(header+20,0);
 for(uint8_t version=0;version<8;version++)for(uint16_t flag=0;flag<256;flag++)for(uint8_t n=0;n<9;n++){
  header[4]=version;header[5]=flag;put32(header+8,samples[n]);snapshot(d,d.begin(header,22));snapshot(d,d.begin(0,0));
 }
 uint32_t serial=0;
 for(uint8_t profile=4;profile<=6;profile+=2){
  const uint8_t bits=profile==4?5:6,limit=1<<bits;
  for(uint8_t delta=0;delta<2;delta++)for(uint8_t old=0;old<limit;old++)
  for(int16_t last=-1;last<limit;last++)for(uint8_t code=0;code<(1u<<(bits+delta));code++)frame(d,profile,delta,old,last,code,serial++);
  for(uint8_t enhanced=0;enhanced<2;enhanced++)for(uint16_t pair=0;pair<512;pair++)for(uint8_t amp=0;amp<16;amp++){
   Writer w;
   if(profile==6){w.put(pair&255,8);w.put(pair>>8,1);w.put(amp,4);w.put(15-amp,4);}
   else{w.put(pair&15,4);w.put(amp&1,1);w.put((pair>>4)&15,4);w.put((amp>>1)&1,1);}
   if(enhanced){w.put(1,1);w.put(pair&63,6);w.put(amp,4);}
   const uint16_t sizes2[3]={w.size(),0,(uint16_t)(w.size()-1)};
   for(uint8_t cut=0;cut<(pair%31==0?3:1);cut++){
    setup(d,w,sizes2[cut],profile|(enhanced?128:0));snapshot(d,d.readSubframe());
   }
  }
 }
 printf("%lu parser cases %016llx\n",(unsigned long)cases,(unsigned long long)digest);
}
