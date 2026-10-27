#include "Lpx4HybridCore.h"
#include "Lpx4Math.h"
#include <stddef.h>
#include <string.h>
// Compile-time amplitude calibration: same compressed bits, same decoder path.
#ifndef LPX4_PWM_GAIN
#define LPX4_PWM_GAIN 130
#endif
#ifndef LPX4_PWM_ROUND
#define LPX4_PWM_ROUND 1
#endif
#if LPX4_PWM_GAIN < 120 || LPX4_PWM_GAIN > 136
#error LPX4_PWM_GAIN out of tested bounds
#endif
// Optional simple excitation paths:1 raw/zero,2 exhausted sparse,4 cached
// zero-delta pitch Rice k0. Zero retains the complete reference decodeCode.
#ifndef LPX4_FAST_EXCITATION
#define LPX4_FAST_EXCITATION 7
#endif
#if LPX4_FAST_EXCITATION < 0 || (LPX4_FAST_EXCITATION & ~7)
#error Unsupported LPX4_FAST_EXCITATION
#endif

#ifdef __AVR__
#include <avr/pgmspace.h>
#define LP_READ_U16(ptr) pgm_read_word((ptr))
#define LP_READ_U8(ptr) pgm_read_byte((ptr))
#define LP_PROGMEM PROGMEM
#else
#define LP_READ_U16(ptr) (*(ptr))
#define LP_READ_U8(ptr) (*(ptr))
#define LP_PROGMEM
#endif
// Preserve signed division's truncation toward zero without AVR libgcc's
// generic 32-bit divide at -Os. All callers use constant powers of two.
static inline __attribute__((always_inline)) int32_t truncShift(int32_t v,uint8_t bits){
    return (v+(v<0?((1L<<bits)-1):0))>>bits;
}

static const uint8_t LP_PROGMEM bitMasks[9]={0,1,3,7,15,31,63,127,255};

// Exact differences of cos_table.inc, not an approximation. Every16th
// half-wave node and its positive drop are retained. A nibble stores the
// next drop minus the current drop plus1 (range0..4); low nibble first.
// Reconstruct at most15 intervening nodes, keeping the drop in0..101.
static const uint16_t LP_PROGMEM cosineCheckpoints[8]={
 8192,8035,7568,6811,5793,4551,3135,1598
};
static const uint8_t LP_PROGMEM cosineSlope[8]={1,21,39,56,72,84,93,99};
static const uint8_t LP_PROGMEM cosineBend[64]={
 65,33,35,50,34,34,19,51,49,34,34,35,65,33,35,34,
 34,19,19,35,34,50,33,19,50,49,33,50,33,34,34,49,
 49,17,35,33,34,33,34,33,49,48,33,33,18,49,32,18,
 18,33,33,17,18,2,18,18,48,32,32,17,33,16,2,18
};
#if LPX4_COMPACT_ONLY
// v5 transmits a5-bit scale; these are exactly originalStep[index*8].
// Its small direct table removes the generic variable-shift reconstruction.
static const uint16_t LP_PROGMEM scaleValues[32]={
 0,0,0,0,0,0,1,1,1,1,2,3,4,6,8,12,
 16,23,33,46,66,93,131,185,262,371,524,741,1049,1483,2097,2966
};
static uint16_t scaleStep(uint8_t index){return LP_READ_U16(&scaleValues[index]);}
#else
static const uint16_t LP_PROGMEM scaleMantissa[16]={
 4194,4380,4573,4776,4987,5208,5439,5680,
 5931,6194,6468,6754,7053,7366,7692,8032
};
// Exact integer reconstruction of all 256 original scale entries (0..4016).
// Decode once per 80-sample block, including zero aliases; no floating point.
static uint16_t scaleStep(uint8_t index){
 const uint16_t mantissa=LP_READ_U16(&scaleMantissa[index&15]);
 return ((mantissa>>(15-(index>>4)))+1)>>1;
}
#endif
// Adjacent cosine nodes share one reflection. The reflected interval starts
// at -hi and has the same hi-lo slope, so negative floor rounding is exact.
// norm is Q12 in 0..4095; adjacent nodes differ by at most 101.
static inline __attribute__((always_inline)) int16_t cosineInterpolate(uint16_t norm){
 uint8_t index=(uint8_t)(norm>>4);
 const uint8_t fraction=(uint8_t)(norm&15);
 const bool negative=index>=128;
 if(negative)index=(uint8_t)(255-index);
 const uint8_t group=index>>4;
 int16_t lo=LP_READ_U16(&cosineCheckpoints[group]);
 uint8_t drop=LP_READ_U8(&cosineSlope[group]);
 for(uint8_t j=group<<4;j<index;j++){
  lo-=drop;
  const uint8_t pair=LP_READ_U8(&cosineBend[j>>1]);
  drop+=((j&1)?(pair>>4):(pair&15))-1;
 }
 const int16_t hi=lo-drop;
 // floor(-drop*f/16) == -ceil(drop*f/16); product is at most1515.
 const uint16_t loss=((uint16_t)drop*fraction+15)>>4;
 return (int16_t)((negative?-hi:lo)-(int16_t)loss);
}


Lpx4HybridCore::Lpx4HybridCore(): data_(0),bytes_(0),
#if !LPX4_ROM_POINTER
 cursor_(0),
#endif
 sampleCount_(0),remaining_(0),sampleRate_(0),preQ14_(0),brightQ14_(0) {
#ifdef __AVR__
 static_assert(offsetof(Lpx4HybridCore,staticSpectrum_)<64,"Hot state exceeds AVR short displacement");
 static_assert(offsetof(Lpx4HybridCore,error_)<64,"Error flag must retain short displacement");
#endif
 resetState();
}
// Shared per-stream parser and synthesis reset. Callers retain input, public
// stream metadata, and remaining-count initialization, including failed begin().
void Lpx4HybridCore::resetState(){
 error_=NONE;initializedFrame_=false;
 subPos_=subIndex_=0;
#if LPX4_BATCHED_REMAINING
 subEnd_=0;
#endif
#if LPX4_COMPACT_ONLY
 bitBuffer_=bitsLeft_=lag_=gain_=ringCursor_=0;blockStep_=0;
#else
 bitBuffer_=bitsLeft_=mode_=blockScale_=riceK_=0;blockStep_=0;
 subType_=lag_=gain_=ringCursor_=quantLimit_=0;
#endif
#if LPX4_ENABLE_SPEECH
 speechProfile_=speechHalf_=0;
#endif
#if LPX4_ENABLE_SPEECH_COMPACT
 speechCompact_=0;
#endif
#if LPX4_V3_FEATURES && !LPX4_COMPACT_ONLY
 formatFeatures_=0;
#endif
#if LPX4_ALLOW_SPARSE
 pulseCount_=pulseIndex_=0;
#endif
 prevDeemph_=prevBright_=0;
#ifdef LPX3_COST_INSTRUMENT
 lsfConverts_=bitCalls_=romByteCalls_=0;
#endif
 lsfCached_=false;staticSpectrum_=false;
#if LPX4_ROTATE_LPC_ANCHORS
 lpcAnchorOffset_=0;
#endif
 memset(prev_,0,sizeof(prev_));memset(cur_,0,sizeof(cur_));
 memset(a_,0,sizeof(a_));memset(hist_,0,sizeof(hist_));
 memset(ringQ_,0,sizeof(ringQ_));
}
int16_t Lpx4HybridCore::clamp(int32_t n,int16_t low,int16_t high){
 return n<low?low:(n>high?high:(int16_t)n);
}
// Bounded ROM access and container setup.
uint8_t Lpx4HybridCore::readByte(){
#ifdef LPX3_COST_INSTRUMENT
 ++romByteCalls_;
#endif
 if(error_)return 0;
#if LPX4_ROM_POINTER
 if(!bytes_){error_=END_OF_ROM;return 0;}
 --bytes_;
 return LP_READ_U8(data_++);
#else
 if(cursor_>=bytes_){error_=END_OF_ROM;return 0;}
 return LP_READ_U8(data_+cursor_++);
#endif
}
uint16_t Lpx4HybridCore::read16(){
 const uint16_t low=readByte();return (uint16_t)(low | (uint16_t)readByte()<<8);
}
uint32_t Lpx4HybridCore::read32(){
 const uint32_t low=read16();return low|((uint32_t)read16()<<16);
}
bool Lpx4HybridCore::begin(const uint8_t* input,uint16_t size){
 data_=input;bytes_=size;
#if !LPX4_ROM_POINTER
 cursor_=0;
#endif
 remaining_=sampleCount_;
 resetState();
 if(!input||size<20){error_=BAD_HEADER;return false;}
 if(readByte()!='L'||readByte()!='4'||readByte()!='H'||readByte()!='Y'){
  error_=BAD_HEADER;return false;
 }
 const uint8_t version=readByte(),flags=readByte();
#if LPX4_COMPACT_ONLY
 if(version!=5 || ((flags&127)!=4 && (flags&127)!=6)){error_=UNSUPPORTED;return false;}
 speechProfile_=flags&127;speechCompact_=1|(flags&128);
#else
#if LPX4_ENABLE_SPEECH_COMPACT
 if(version==5 && ((flags&127)==4 || (flags&127)==6)){
  speechProfile_=flags&127;speechCompact_=1|(flags&128);
 }else
#endif
#if LPX4_ENABLE_SPEECH
 if(version==4 && (flags==4 || flags==6))speechProfile_=flags;
 else
#endif
 {
#if LPX4_V3_FEATURES
 if(version==3 && (flags&3)==3 && !(flags&~(3|LPX4_V3_FEATURES)))formatFeatures_=flags&124;
 else if(version!=2||flags!=3){error_=UNSUPPORTED;return false;}
#else
 if(version!=2||flags!=3){error_=UNSUPPORTED;return false;}
#endif
 }
#endif
 sampleRate_=read16();sampleCount_=read32();preQ14_=read16();brightQ14_=read16();
 remaining_=sampleCount_;
#if LPX4_BATCHED_REMAINING
 subEnd_=remaining_<20?(uint8_t)remaining_:20;
#endif
 const uint16_t frames=read16(),blocks=read16();
#if LPX4_COMPACT_ONLY
 const bool geometry=frames==320 && blocks==160;
 const uint16_t payload=read16();
 if(sampleCount_>64000 || !sampleCount_ || (uint32_t)size!=22UL+payload){
  error_=BAD_HEADER;return false;
 }
#else
 bool geometry=frames==160 && blocks==80;
#if LPX4_ENABLE_SPEECH
 if(speechProfile_){
  geometry=frames==320 && blocks==160;
  // Full final packet is mandatory, even for a partial sample tail. Bound
  // the count before addition/multiplication; reject truncation at begin().
  bool complete;
#if LPX4_ENABLE_SPEECH_COMPACT
  if(speechCompact_){const uint16_t payload=read16();complete=(uint32_t)size==22UL+payload;}
  else
#endif
  // Accepted counts are <=64000: count+319 and the byte length fit uint16.
  // Larger counts are still rejected by the full-width guard below.
  complete=size==(uint16_t)(20+(((uint16_t)sampleCount_+319u)/320u)*(speechProfile_==4?20:30));
  if(sampleCount_>64000 || !sampleCount_ || !complete){
   error_=BAD_HEADER;return false;
  }
 }
#endif
#endif
 if(error_||sampleRate_!=8000||!sampleCount_||!geometry||
    preQ14_>16384||brightQ14_>11469){error_=BAD_HEADER;return false;}
 return true;
}
// LSB-first bit and entropy readers.
// Share cache/refill logic and its single diagnostic call with readBits.
uint8_t Lpx4HybridCore::readOne(){return readBits(1);}

#if !LPX4_COMPACT_ONLY
// Consume the mandatory two-bit Huffman prefix in one cached operation.
// Zero retains the original per-bit path; instrumentation preserves its costs.
#ifndef LPX4_FAST_HUFFMAN3
#define LPX4_FAST_HUFFMAN3 1
#endif
#if LPX4_FAST_HUFFMAN3 != 0 && LPX4_FAST_HUFFMAN3 != 1
#error LPX4_FAST_HUFFMAN3 must be 0 or 1
#endif
int8_t Lpx4HybridCore::readHuffman3(){
#if LPX4_FAST_HUFFMAN3 && !defined(LPX3_COST_INSTRUMENT)
 uint8_t prefix;
 if(bitsLeft_>=2){prefix=bitBuffer_&3;bitBuffer_>>=2;bitsLeft_-=2;}
 else prefix=readBits(2);
 if(prefix==0)return -1;
 if(prefix==1)return 0;
 if(prefix==2)return readOne()?-2:2;
#else
 if(!readOne()){
  if(!readOne())return -1;
  return readOne()?-2:2;
 }
 if(!readOne())return 0;
#endif
 if(readOne())return 1;
 if(!readOne())return 3;
 return readOne()?-3:-4;
}
#endif
uint8_t Lpx4HybridCore::readBits(uint8_t n){
#ifdef LPX3_COST_INSTRUMENT
 ++bitCalls_;
#endif
 const uint8_t available=bitsLeft_;
 uint8_t out;
 if(available>=n){
  out=bitBuffer_&LP_READ_U8(&bitMasks[n]);
  bitBuffer_>>=n;bitsLeft_=available-n;
 }else{
  const uint8_t extra=readByte(),need=n-available;
  out=bitBuffer_|((extra&LP_READ_U8(&bitMasks[need]))<<available);
  bitBuffer_=extra>>need;bitsLeft_=8-need;
 }
 return out;
}
#if LPX4_ENABLE_SPEECH_COMPACT
uint8_t Lpx4HybridCore::readSpeechRice(uint8_t k,uint8_t width){
 uint8_t high=0;
 while(high<8 && !readOne()){
  if(error_)return 0;
  ++high;
 }
 if(high==8)return readBits(width);
 return (high<<k)|(k?readBits(k):0);
}
#endif
// Container parsing: frame, block, and subframe headers.
bool Lpx4HybridCore::readFrame(){
 for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i];
#if LPX4_ENABLE_SPEECH
#if !LPX4_COMPACT_ONLY
 if(speechProfile_){
#else
 {
#endif
  staticSpectrum_=true;
  if(!speechHalf_){
   const uint8_t bits=speechProfile_==4?5:6,shift=10-bits;
#if LPX4_ENABLE_SPEECH_COMPACT
#if !LPX4_COMPACT_ONLY
   if(speechCompact_){
#else
   {
#endif
    if(!readOne()){
     if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
    }else{
     const bool delta=readOne()!=0;
     if(delta&&!initializedFrame_){error_=CORRUPT_STREAM;return false;}
     const uint8_t k=bits-4-(uint8_t)delta;
     int16_t last=-1;
     for(uint8_t i=0;i<10;i++){
      const uint8_t code=readSpeechRice(k,bits+(delta?1:0));
      // Compact Rice codes use at most seven bits: delta is -64..63.
      const int8_t difference=(code&1)?-(int8_t)((code+1)>>1):(int8_t)(code>>1);
      const int16_t value=delta?((prev_[i]>>shift)+difference):last+1+code;
      if(error_)return false;
      if(value<=last || value>=((speechProfile_-2)<<4)){error_=CORRUPT_STREAM;return false;}
      const int16_t v=(value<<shift)+(1u<<(shift-1));
      if(initializedFrame_ && v!=prev_[i])staticSpectrum_=false;
      cur_[i]=v;last=value;
     }
    }
   }
#if !LPX4_COMPACT_ONLY
   else
#endif
#endif
#if !LPX4_COMPACT_ONLY
   {
   for(uint8_t i=0;i<10;i++){
    const int16_t v=((uint16_t)readBits(bits)<<shift)+(1u<<(shift-1));
    if(i && v<=cur_[i-1]){error_=CORRUPT_STREAM;return false;}
    if(initializedFrame_ && v!=prev_[i])staticSpectrum_=false;
    cur_[i]=v;
   }
   if(speechProfile_==6 && readBits(6)){error_=CORRUPT_STREAM;return false;}
   }
#endif
  }
  if(!initializedFrame_)for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i];
  initializedFrame_=true;speechHalf_^=1;
#if LPX4_COMPACT_ONLY
  const uint8_t blockScale=readBits(5);
#else
  mode_=6;quantLimit_=32;
  blockScale_=readBits(5)<<3;
#endif
  lag_=18+readBits(7);gain_=readBits(3)<<1;
#if LPX4_COMPACT_ONLY
  blockStep_=scaleStep(blockScale);
#else
  blockStep_=scaleStep(blockScale_);
#endif
#if LPX4_EXCITATION_Q4
  blockStep_<<=4;
#endif
  return !error_;
 }
#endif
#if !LPX4_COMPACT_ONLY
 if(!readOne()){
  if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
  staticSpectrum_=true;
  return !error_;
 }
 int16_t v[10];
 if(!readOne()){
  // LSF10 absolute: 10 * exactly 10 bits (no pad to 13-byte frame).
  for(uint8_t i=0;i<10;i++)v[i]=(int16_t)(readBits(8)|((uint16_t)readBits(2)<<8));
 }else{
  if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
#if LPX4_V3_FEATURES & 64
  const uint8_t coding=(formatFeatures_&64)?readBits(2):readOne();
#else
  // Preserve the v2 Boolean branch/code generation without optional LSF Rice.
  const bool coding=readOne()!=0;
#endif
  for(uint8_t i=0;i<10;i++){
   int8_t d=0;
   if(coding==1)d=(int8_t)readBits(8);
#if LPX4_V3_FEATURES & 64
   else if(coding>=2){
    const uint8_t k=coding==2?0:2;
    uint8_t high=0;
    while(high<8 && !readOne()){
     if(error_){error_=CORRUPT_STREAM;return false;}++high;
    }
    if(high==8)d=(int8_t)readBits(8);
    else{
     const uint8_t z=(high<<k)|(k?readBits(k):0);
     d=(z&1)?-(int8_t)((z+1)>>1):(int8_t)(z>>1);
    }
   }
#endif
   else {
    uint8_t z=0;
    while(!readOne()){
     if(error_||++z>7){error_=CORRUPT_STREAM;return false;}
    }
    const int8_t hi=(z&1)?-(int8_t)((z+1)>>1):(int8_t)(z>>1);
    const uint8_t lo=readOne()?readBits(5):0;
    d=(int8_t)((int16_t)hi*32+lo);
   }
   v[i]=cur_[i]+d;
  }
 }
 if(error_)return false;
 staticSpectrum_=true;
 for(uint8_t i=0;i<10;i++){
  if(v[i]<0||v[i]>1023){error_=CORRUPT_STREAM;return false;}
  if(initializedFrame_ && v[i]!=prev_[i])staticSpectrum_=false;
  cur_[i]=v[i];
 }
 if(!initializedFrame_)for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i];
 initializedFrame_=true;return true;
#endif
}
#if !LPX4_COMPACT_ONLY
bool Lpx4HybridCore::readBlock(){
#if LPX4_ENABLE_SPEECH
 if(speechProfile_)return !error_;
#endif
#if LPX4_V3_FEATURES & 8
 if(!(formatFeatures_&8) || readOne())
#endif
 mode_=readBits(3); // source bit depth, 0 or 2..6
 if(mode_!=0 && (mode_<2 || mode_>6)){error_=CORRUPT_STREAM;return false;}
 quantLimit_=mode_?(1u<<(mode_-1)):0;
#if LPX4_V3_FEATURES & 32
 if((formatFeatures_&32) && !mode_)return !error_;
#endif
#if LPX4_V3_FEATURES & 4
 if((formatFeatures_&4) && !readOne())return !error_;
#endif
 uint8_t q=0;
 while(q<6 && !readOne()){
  if(error_){error_=CORRUPT_STREAM;return false;}++q;
 }
 if(q==6)blockScale_=readBits(8);
 else{
  const uint8_t z=(uint8_t)((q<<4)|readBits(4));
  const int16_t d=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
  const int16_t target=(int16_t)blockScale_+d;
  if(target<0||target>255){error_=CORRUPT_STREAM;return false;}
  blockScale_=(uint8_t)target;
 }
 blockStep_=scaleStep(blockScale_);
#if LPX4_EXCITATION_Q4
 blockStep_<<=4; // 4016*16=64256 fits unsigned16.
#endif
 return !error_;
}
#endif
bool Lpx4HybridCore::readSubframe(){
#if LPX4_ENABLE_SPEECH
#if !LPX4_COMPACT_ONLY
 if(speechProfile_){
  subType_=2;pulseIndex_=0;pulseCount_=2;
#else
 {
  pulseIndex_=0;pulseCount_=2;
#endif
#if LPX4_ENABLE_SPEECH_COMPACT
  uint16_t pair=0;
  uint8_t second=0;
#if LPX4_COMPACT_ONLY
  if(speechProfile_==6){
#else
  if(speechCompact_ && speechProfile_==6){
#endif
   pair=readBits(8);pair|=(uint16_t)readOne()<<8;
   if(pair>=400){error_=CORRUPT_STREAM;return false;}
   // For n=0..399: floor(n/20)=floor(floor(n/4)/5).
   // x*205>>10 is exact /5 for x=0..99; product fits unsigned16.
   second=((uint16_t)(uint8_t)(pair>>2)*205u)>>10;
  }
#endif
  for(uint8_t i=0;i<2;i++){
   uint8_t pos;
   int8_t amp;
   if(speechProfile_==4){
    pos=readBits(4);pos+=(pos+2)>>2;
    amp=readOne()?8:-8;
   }else{
#if LPX4_ENABLE_SPEECH_COMPACT
#if LPX4_COMPACT_ONLY
    pos=i?second:(uint8_t)(pair-second*20);
#else
    if(speechCompact_)pos=i?second:(uint8_t)(pair-second*20);
    else
#endif
#endif
#if !LPX4_COMPACT_ONLY
    pos=readBits(5);
#endif
    const uint8_t raw=readBits(4);
    amp=raw<8?(int8_t)raw:(int8_t)((int16_t)raw-16);
    if(pos>=20){error_=CORRUPT_STREAM;return false;}
   }
   pulsePos_[i]=pos+i*20;pulseAmp_[i]=amp;
  }
#if LPX4_ENABLE_SPEECH_COMPACT
  if((speechCompact_&128) && readOne()){
   const uint8_t pos=readBits(6),raw=readBits(4);
   const int8_t amp=raw<8?(int8_t)raw:(int8_t)((int16_t)raw-16);
   if(pos>=40){error_=CORRUPT_STREAM;return false;}
   uint8_t at=0;
   while(at<2 && pulsePos_[at]<pos)++at;
   if(at<2 && pulsePos_[at]==pos)pulseAmp_[at]+=amp;
   else{
    for(uint8_t j=2;j>at;--j){pulsePos_[j]=pulsePos_[j-1];pulseAmp_[j]=pulseAmp_[j-1];}
    pulsePos_[at]=pos;pulseAmp_[at]=amp;pulseCount_=3;
   }
  }
#endif
  return !error_;
 }
#endif
#if !LPX4_COMPACT_ONLY
#if LPX4_V3_FEATURES & 32
 if((formatFeatures_&32) && !mode_){
  subType_=riceK_=0;
#if LPX4_ALLOW_SPARSE
  pulseIndex_=pulseCount_=0;
#endif
  return !error_;
 }
#endif
#if LPX4_V3_FEATURES & 16
 const bool repeated=(formatFeatures_&16) && !readOne();
 if(!repeated)
#endif
 subType_=readBits(2);
#if LPX4_ALLOW_SPARSE
 pulseIndex_=pulseCount_=0;
#endif
 if(subType_==3){error_=CORRUPT_STREAM;return false;}
 if(subType_==0){
#if LPX4_V3_FEATURES & 16
   if(!repeated)
#endif
   riceK_=readBits(3);
   if(riceK_==7 && mode_!=3){error_=CORRUPT_STREAM;return false;}
 }else{
#if LPX4_V3_FEATURES & 16
   if(!repeated){
#endif
   lag_=(uint8_t)(18+readBits(7));
   gain_=readBits(5);
#if LPX4_V3_FEATURES & 16
   }
#endif
   if(lag_>145){error_=CORRUPT_STREAM;return false;}
   if(subType_==1){
#if LPX4_V3_FEATURES & 16
    if(!repeated)
#endif
    riceK_=readBits(3);
   }
   else{
#if LPX4_ALLOW_SPARSE
     pulseCount_=readBits(4);
     if(pulseCount_>LPX4_MAX_PULSES){error_=CORRUPT_STREAM;return false;}
     const uint8_t remaining=(uint8_t)(remaining_>=40?40:remaining_);
     for(uint8_t i=0;i<pulseCount_;i++){
       pulsePos_[i]=readBits(6);
       const uint8_t z=readBits(5);
       pulseAmp_[i]=(z&1)?-(int8_t)((z+1)>>1):(int8_t)(z>>1);
       if(pulsePos_[i]>=remaining || (i && pulsePos_[i]<=pulsePos_[i-1])){
         error_=CORRUPT_STREAM;return false;
       }
     }
#else
     error_=UNSUPPORTED;
     return false;
#endif
   }
 }
 return !error_;
#endif
}
// Excitation reconstruction and quantized pitch history.
// 0 keeps the reference predictor, bit1 narrows the proven result,
// bit2 bypasses zero history, bit4 additionally bypasses zero gain.
#ifndef LPX4_FAST_PITCH
#define LPX4_FAST_PITCH 3
#endif
#if LPX4_FAST_PITCH < 0 || (LPX4_FAST_PITCH & ~7) || (LPX4_FAST_PITCH && !(LPX4_FAST_PITCH&1))
#error Unsupported LPX4_FAST_PITCH
#endif
int16_t Lpx4HybridCore::pitchPredict() const{
#if LPX4_FAST_PITCH
#if !LPX4_COMPACT_ONLY
 if(!mode_)return 0;
#endif
 const int8_t x=ringQ_[(uint8_t)(ringCursor_-lag_)];
#if LPX4_FAST_PITCH&2
 if(!x)return 0;
#endif
#if LPX4_FAST_PITCH&4
 if(!gain_)return 0;
#endif
 int8_t v=lpx4PitchQ4(x,gain_);
// v5 gain is0..14 and history is-32..31: prediction is already-28..27.
#if !LPX4_COMPACT_ONLY
 const int8_t low=-(int8_t)quantLimit_,high=(int8_t)(quantLimit_-1);
 if(v<low)v=low;
 if(v>high)v=high;
#endif
 return v;
#else
 const int8_t x=ringQ_[(uint8_t)(ringCursor_-lag_)];
 int16_t v=(int16_t)(((int8_t)gain_*x+8)>>4);
#if !LPX4_COMPACT_ONLY
 if(!mode_)return 0;
 const int16_t lim=quantLimit_;
 if(v < -lim)v=-lim;
 if(v >= lim)v=lim-1;
#endif
 return v;
#endif
}
#if !LPX4_COMPACT_ONLY
// Valid decodeCode callers have error==NONE. Nonzero cache contains a
// terminator within bitsLeft (all unused cache bits are zero by construction).
// Empty/all-zero caches retain the exact bounded refill/error path.
#ifndef LPX4_FAST_UNARY
#define LPX4_FAST_UNARY 1
#endif
#if LPX4_FAST_UNARY < 0 || LPX4_FAST_UNARY > 2
#error LPX4_FAST_UNARY must be 0,1 or2
#endif
#if LPX4_FAST_UNARY==2
static const uint8_t LP_PROGMEM unaryNibble[16]={4,0,1,0,2,0,1,0,3,0,1,0,2,0,1,0};
#endif
bool Lpx4HybridCore::readUnary8(uint8_t& high){
 high=0;
#if LPX4_FAST_UNARY
 if(bitBuffer_){
   uint8_t cache=bitBuffer_;
#if LPX4_FAST_UNARY==2
   if(!(cache&15)){cache>>=4;high=4;}
   high+=LP_READ_U8(&unaryNibble[cache&15]);
   cache=bitBuffer_>>high;
#else
   while(!(cache&1)){cache>>=1;++high;}
#endif
   bitBuffer_=cache>>1;bitsLeft_-=high+1;
#ifdef LPX3_COST_INSTRUMENT
   bitCalls_+=high+1;
#endif
   return true;
 }
#endif
 while(!readOne()){
   if(error_||++high>8){error_=CORRUPT_STREAM;return false;}
 }
 return true;
}
#endif
bool Lpx4HybridCore::decodeCode(int8_t& q){
#if LPX4_COMPACT_ONLY
 int16_t decoded=pitchPredict();
 if(pulseIndex_<pulseCount_ && pulsePos_[pulseIndex_]==(subPos_+((subIndex_&1)?20:0))){
  decoded+=pulseAmp_[pulseIndex_++];
 }
 if(error_)return false;
 if(decoded < -32)decoded=-32;
 if(decoded > 31)decoded=31;
 q=(int8_t)decoded;ringQ_[ringCursor_++]=q;
 return true;
#else
 int16_t decoded=0;
 if(subType_==0){
   if(!mode_)decoded=0;
   else if(riceK_==7){
     decoded=readHuffman3();
   }else if(riceK_){
     uint8_t high;
     if(!readUnary8(high))return false;
     const uint16_t z=(uint16_t)((high<<riceK_)|readBits(riceK_));
     decoded=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
   }else decoded=(int16_t)readBits(mode_)-(int16_t)quantLimit_;
 }else{
   decoded=pitchPredict();
   int16_t d=0;
   if(subType_==1){
     if(riceK_==7)d=(int8_t)readBits(8);
     else{
       uint8_t high;
       if(!readUnary8(high))return false;
       const uint16_t z=(uint16_t)((high<<riceK_) | (riceK_?readBits(riceK_):0));
       d=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
     }
   }
#if LPX4_ALLOW_SPARSE
   else if(pulseIndex_<pulseCount_ && pulsePos_[pulseIndex_]==(subPos_+((subIndex_&1)?20:0))){
       d=pulseAmp_[pulseIndex_++];
   }
#endif
   decoded+=d;
   if(subType_==2){
     if(!mode_)decoded=0;
     else{
       const int16_t lim=quantLimit_;
       if(decoded < -lim)decoded=-lim;
       if(decoded >= lim)decoded=lim-1;
     }
   }
 }
 if(error_)return false;
 if(mode_){
   const int16_t lim=quantLimit_;
   if(decoded < -lim || decoded >= lim){error_=CORRUPT_STREAM;return false;}
 }else if(decoded){error_=CORRUPT_STREAM;return false;}
 q=(int8_t)decoded;
 ringQ_[ringCursor_++]=q;
 return true;
#endif
}
// Guard the 32x16 product on pathological/invalid LPX3 LSF vectors.
// Normal spectra take the single-multiply fast path; split product only if
// absolute polynomial coefficient would overflow signed int32 when *8192.
static inline int32_t polyMulQ12(int32_t v,int16_t c){
    if(v<=250000L && v>=-250000L)return lpx4Shift12(v*c);
    const int32_t hi=truncShift(v,4);
    int8_t rem=(uint8_t)v&15;
    if(v<0 && rem)rem-=16;
    // Preserve the original separate floors of the two split products.
    return ((hi*c)>>8)+lpx4Shift12(lpx4Mul8x16(rem,c));
}
// LSF->LPC polynomial. Independent Q12 multiplication (no floats/trig in AVR).
void Lpx4HybridCore::polyFactor(int32_t* p,int16_t c,uint8_t n){
    // Multiply by 1+c*z^-1+z^-2 IN PLACE, descending to preserve original
    // p[j-1] and p[j-2]. Eliminates 12*4=48 bytes of SRAM and two passes.
    // Retain the same ascending-contribution order as the old polyTmp method.
    p[n+1]=p[n-1];
    p[n]=p[n-2]+polyMulQ12(p[n-1],c);
    for(uint8_t j=(uint8_t)(n-1);j>=2;--j){
        p[j]=p[j-2]+polyMulQ12(p[j-1],c)+p[j];
    }
    // p[0] is initialized to 4096 and never changed by any factor.
    p[1]=c+p[1];
}
// LPC spectrum conversion and anchor interpolation.
#ifndef LPX3_LPC_SEGMENTS
#define LPX3_LPC_SEGMENTS 2
#endif
#if LPX3_LPC_SEGMENTS!=1 && LPX3_LPC_SEGMENTS!=2 && LPX3_LPC_SEGMENTS!=4
#error LPX3_LPC_SEGMENTS must be 1,2,4
#endif
// LSF->LPC only on predicted polynomial anchors, not every subframe.
// Anchor arithmetic is identical to the reference integer polynomial at t=0..16.
// PCM synthesis still uses the exact same 10-pole filter and quantized residual.
void Lpx4HybridCore::convertLsfAt(uint8_t t,int16_t* out){
#ifdef LPX3_COST_INSTRUMENT
    ++lsfConverts_;
#endif
    polyP_[0]=polyQ_[0]=4096;
    for(uint8_t i=0;i<10;i++){
        const int16_t cc=(int16_t)-cosineInterpolate(lpx4LsfNorm10(prev_[i],cur_[i],t));
        // P/Q polynomials are independent; each pair retains the same degree.
        int32_t* p=(i&1)?polyQ_:polyP_;
        if(i<2){
            // Exact (1 +/- z) first factors; no rounded multiplication.
            const int16_t unit=(i&1)?-4096:4096;
            p[1]=unit+cc;p[2]=4096+((i&1)?-cc:cc);p[3]=unit;
        }else polyFactor(p,cc,(uint8_t)((i&254)+2));
    }
    for(uint8_t i=0;i<10;i++)out[i]=clamp(truncShift(polyP_[i+1]+polyQ_[i+1],1),-32767,32767);
}
void Lpx4HybridCore::interpolateLsf(uint8_t sub){
#if LPX4_ROTATE_LPC_ANCHORS
    int16_t* curLpc=lpcAnchors_+lpcAnchorOffset_;
#else
    int16_t* curLpc=curLpc_;
    int16_t* prevLpc=prevLpc_;
#endif
    // An unchanged LSF vector has identical polynomial anchors and no LPC
    // interpolation. The cached endpoint is valid across repeated frames.
    if(staticSpectrum_){
        if(!lsfCached_){convertLsfAt(0,curLpc);lsfCached_=true;}
        // The endpoint is unchanged for the whole frame. Refresh a_ at its
        // first subframe, because the previous dynamic frame ended at a midpoint.
#if !LPX4_ROTATE_LPC_ANCHORS
        if(sub==0)for(uint8_t i=0;i<10;i++)prevLpc[i]=curLpc[i];
#endif
#ifdef LPX3_BANDWIDTH_EXPAND_Q14
        // nextCore expands a_ after interpolation: reload before every expansion.
        for(uint8_t i=0;i<10;i++)a_[i]=curLpc[i];
#else
        if(sub==0)for(uint8_t i=0;i<10;i++)a_[i]=curLpc[i];
#endif
        return;
    }
#if LPX4_ROTATE_LPC_ANCHORS
    int16_t* prevLpc=lpcAnchors_+(lpcAnchorOffset_^10);
#endif
    // Segment width in t=0..16; at most one polynomial conversion per
    // 20-sample subframe after the initial frame (two at startup).
    const uint8_t width=(uint8_t)(16/LPX3_LPC_SEGMENTS);
    const uint8_t subframesPerSegment=(uint8_t)(8/LPX3_LPC_SEGMENTS);
    if(sub%subframesPerSegment==0){
#if LPX4_ROTATE_LPC_ANCHORS
        if(sub==0&&!lsfCached_)convertLsfAt(0,prevLpc);
        else{
            int16_t* scratch=prevLpc;prevLpc=curLpc;curLpc=scratch;
            lpcAnchorOffset_^=10;
        }
#else
        if(sub==0){
            if(lsfCached_){
                // Last endpoint of prior frame was this frame's old LSF.
                for(uint8_t i=0;i<10;i++)prevLpc[i]=curLpc[i];
            }else convertLsfAt(0,prevLpc);
        }else{
            for(uint8_t i=0;i<10;i++)prevLpc[i]=curLpc[i];
        }
#endif
        const uint8_t anchor=(uint8_t)(((sub/subframesPerSegment)+1)*width);
        convertLsfAt(anchor,curLpc);
        lsfCached_=true;
    }
    const uint8_t t=(uint8_t)(sub*2+1);
    const uint8_t localT=(uint8_t)(t%width);
    for(uint8_t i=0;i<10;i++){
        a_[i]=lpx4LpcInterpolate(prevLpc[i],curLpc[i],localT,
            LPX3_LPC_SEGMENTS==1?4:LPX3_LPC_SEGMENTS==2?3:2);
    }

}

// AVR PWM firmware uses the direct sample path. The optional signed-output
// interface shares the same arithmetic, selected independently of memory I/O.
#if defined(__AVR__) && !defined(LPX4_ENABLE_PCM16)
bool Lpx4HybridCore::next(uint8_t& pcm){
#else
bool Lpx4HybridCore::nextCore(int16_t& postfilterQ14){
#endif
#if LPX4_BATCHED_REMAINING
    if(error_||subPos_==subEnd_)return false;
#else
    if(error_||!remaining_)return false;
#endif
    if(subPos_==0){
        // All frame/block/excitation headers coincide with a 20-sample boundary.
        if(subIndex_==0&&!readFrame())return false;
#if !LPX4_COMPACT_ONLY
        if(!(subIndex_&3)&&!readBlock())return false;
#endif
        if(!(subIndex_&1)&&!readSubframe())return false;
        interpolateLsf(subIndex_);
#ifdef LPX3_BANDWIDTH_EXPAND_Q14
        // Bandwidth expansion a[k] *= gamma^(k+1), once per 20 samples.
        uint16_t weight=16384;
        for(uint8_t k=0;k<10;k++){
            weight=(uint16_t)(((int32_t)weight*LPX3_BANDWIDTH_EXPAND_Q14+8192)>>14);
            a_[k]=clamp(((int32_t)a_[k]*weight+8192)>>14,-32767,32767);
        }
#endif
    }
    int8_t q=0;
#if LPX4_COMPACT_ONLY
#if LPX4_FAST_EXCITATION&2
    if(pulseIndex_>=pulseCount_){q=(int8_t)pitchPredict();ringQ_[ringCursor_++]=q;}
    else
#endif
    if(!decodeCode(q))return false;
#else
#if LPX4_FAST_EXCITATION
    bool simple=false;
    if((LPX4_FAST_EXCITATION&1) && subType_==0 && (!mode_ || !riceK_)){
        q=mode_?(int8_t)((int16_t)readBits(mode_)-quantLimit_):0;
        if(error_)return false;
        // A raw code is already within the validated source bit width.
        simple=true;
    }
#if LPX4_ALLOW_SPARSE
    else if((LPX4_FAST_EXCITATION&2) && subType_==2 && pulseIndex_>=pulseCount_){
        // No pulse remains: pitchPredict has already performed saturation.
        q=(int8_t)pitchPredict();simple=true;
    }
#endif
    else if((LPX4_FAST_EXCITATION&4) && subType_==1 && !riceK_ && bitsLeft_ && (bitBuffer_&1)){
        // Unary terminator1 with k0 is exactly delta0; consume only that bit.
        bitBuffer_>>=1;--bitsLeft_;
#ifdef LPX3_COST_INSTRUMENT
        ++bitCalls_;
#endif
        q=(int8_t)pitchPredict();simple=true;
    }
    if(simple)ringQ_[ringCursor_++]=q;
    else
#endif
    if(!decodeCode(q))return false;
#endif
#ifdef LPX3_Q_DIAG
    lastQ_=q;
#endif
    const uint16_t step=blockStep_;
#if LPX4_EXCITATION_Q4
    const int32_t excitation=lpx4Mul8xU16(q,step);
#else
    // q is signed8 and the exact reconstructed step is 0..4016.
    const int32_t excitation=lpx4Excitation(q,step);
#endif
#if LPX4_LPC_RING
    // subPos already repeats every20 samples; no separate ring cursor is needed.
    int16_t* history=hist_+(subPos_<10?subPos_:subPos_-10)+10;
    int16_t pred=lpx4Clip15From24(lpx4SynthesisRingQ12<LPX4_EXCITATION_Q4>(excitation,a_,history));
    history[0]=history[10]=pred;
#else
    int16_t pred=lpx4Clip15From24(lpx4SynthesisQ12<LPX4_EXCITATION_Q4>(excitation,a_,hist_));
    hist_[0]=pred;
#endif
    int16_t deemph=preQ14_?lpx4AddClip15(pred,lpx4AttenuateQ14(preQ14_,prevDeemph_)):pred;
    prevDeemph_=deemph;
    int16_t clipped=lpx4ClipQ14(deemph);
    // Header validation limits brightness to11469; prevBright/clipped are
    // +/-16384. The un-clipped difference is within +/-27853, signed16-safe.
    int16_t b=brightQ14_?lpx4ClipQ14((int16_t)(clipped-lpx4AttenuateQ14(brightQ14_,prevBright_))):clipped;
    prevBright_=clipped;
    // Preserve the signed post-deemphasis/post-brightness output BEFORE PWM.
    // This is the exact integer sample used by both optional 16-bit output
    // and legacy PWM conversion; no 8-bit quantization has happened yet.
#if defined(__AVR__) && !defined(LPX4_ENABLE_PCM16)
    // Original PWM transfer function for the existing ATmega328P firmware.
#if LPX4_PWM_ROUND
    pcm=lpx4PwmQ14(b,LPX4_PWM_GAIN);
#else
    int16_t duty=(int16_t)(128+((int32_t)b*LPX4_PWM_GAIN)/16384);
    pcm=(uint8_t)clamp(duty,0,255);
#endif
#else
    postfilterQ14 = b;
#endif
#if !LPX4_BATCHED_REMAINING
    --remaining_;
#endif
    ++subPos_;
    if(subPos_==20){
        subPos_=0;
#if LPX4_BATCHED_REMAINING
        remaining_-=20;
        subEnd_=remaining_<20?(uint8_t)remaining_:20;
#endif
        if(++subIndex_==8)subIndex_=0;
#if LPX4_ENABLE_SPEECH_COMPACT
        // A complete final packet must consume the declared payload, with
        // only zero bits left in its final byte. Partial sample tails retain
        // the documented unconsumed-padding behavior.
#if LPX4_COMPACT_ONLY
        if(!remaining_ && !speechHalf_){
#else
        if(speechCompact_ && !remaining_ && !speechHalf_){
#endif
#if LPX4_ROM_POINTER
            const bool trailing=bytes_!=0;
#else
            const bool trailing=cursor_!=bytes_;
#endif
            if(trailing || bitBuffer_){error_=CORRUPT_STREAM;return false;}
        }
#endif
    }
    return true;
}

// Legacy 8-bit output retained for unchanged AVR/Arduino playback.
#if !defined(__AVR__) || defined(LPX4_ENABLE_PCM16)
bool Lpx4HybridCore::next(uint8_t& pcm){
    int16_t b;
    if(!nextCore(b))return false;
#if LPX4_PWM_ROUND
    pcm=lpx4PwmQ14(b,LPX4_PWM_GAIN);
#else
    const int16_t duty=(int16_t)(128+((int32_t)b*LPX4_PWM_GAIN)/16384);
    pcm=(uint8_t)clamp(duty,0,255);
#endif
    return true;
}

// Raw signed signal after LPC synthesis, deemphasis and brightness filter,
// nominal Q14, valid range -16384..+16384. Bypasses PWM completely.
// Only enable these additional output functions on AVR when explicitly needed;
// the usual PWM firmware retains its old size/cost requirements.
bool Lpx4HybridCore::nextQ14(int16_t& out){return nextCore(out);}

// Signed full-scale linear PCM16 for comparison against reference PCM16 WAV.
// No gain fitting or truncation to 8 bits. +16384 maps to +32767 (saturation),
// -16384 to -32768; input waveform is compared against WAV /32768.0.
bool Lpx4HybridCore::nextS16(int16_t& out){
    int16_t b;
    if(!nextCore(b))return false;
    out=clamp((int32_t)b*2,-32768,32767);
    return true;
}
#endif
