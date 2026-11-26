#include "decoder.h"
#include <string.h>
#ifdef __AVR__
#include <avr/pgmspace.h>
#define LG1_ROM PROGMEM
#else
#define LG1_ROM
#endif

namespace lbg1 {
namespace {
const uint16_t scaleSteps[32] LG1_ROM={
 0,0,0,0,0,0,1,1,1,1,2,3,4,6,8,12,16,23,33,46,66,93,131,185,262,371,524,741,1049,1483,2097,2966
};
const int16_t logarithms[32] LG1_ROM={
 -1,-1,-1,-1,-1,-1,0,0,0,0,256,406,512,662,768,918,1024,1158,1291,1414,1547,1674,1801,1928,2057,2185,2313,2441,2569,2697,2825,2953
};
const uint16_t exp2Fraction[17] LG1_ROM={
 4096,4277,4467,4664,4871,5087,5312,5547,5793,6049,6317,6597,6889,7194,7512,7845,8192
};
const uint8_t highCoordinates[25] LG1_ROM={
 0,4,8,12,16,32,36,40,44,48,64,68,72,76,80,96,100,104,108,112,128,132,136,140,144
};
uint16_t romWord(const uint16_t* p){
#ifdef __AVR__
 return pgm_read_word(p);
#else
 return *p;
#endif
}
uint8_t romByte(const uint8_t* p){
#ifdef __AVR__
 return pgm_read_byte(p);
#else
 return *p;
#endif
}
void copy10(int16_t* to,const int16_t* from){for(uint8_t i=0;i<10;++i)to[i]=from[i];}
}

uint16_t stepForScale(uint8_t scale){return scale<32?romWord(scaleSteps+scale):0;}
int16_t logStart(uint8_t scale){return scale<32?(int16_t)romWord(reinterpret_cast<const uint16_t*>(logarithms+scale)):-1;}
uint16_t logToStep(int16_t q){
 if(q<0||q>3071)return 0;
 const uint8_t node=(uint8_t)q>>4;
 const uint16_t lo=romWord(exp2Fraction+node),hi=romWord(exp2Fraction+node+1);
 const uint16_t base=lo+(((hi-lo)*(uint8_t)(q&15)+8)>>4);
 return (uint16_t)((((uint32_t)base<<(q>>8))+2048)>>12);
}

Decoder::Decoder(){reset();}
void Decoder::reset(){
 memset(this,0,sizeof(*this));input_=0;reader_=0;context_=0;
 firstFrame_=true;lag_=18;extraPosition_=255;
}
bool Decoder::fail(uint8_t code){if(!error_)error_=code;return false;}
uint8_t Decoder::readAt(uint16_t offset){
 if(error_)return 0;
 if(offset>=length_){fail(TRUNCATED);return 0;}
 if(reader_){uint8_t value=0;if(!reader_(context_,offset,&value))fail(READ_FAILURE);return value;}
 if(!input_){fail(READ_FAILURE);return 0;}
 return romByte(input_+offset);
}
uint16_t Decoder::readWord(uint8_t at){uint16_t lo=readAt(at);return lo|((uint16_t)readAt(at+1)<<8);}
bool Decoder::begin(const uint8_t* data,uint16_t size){reset();input_=data;length_=size;return header();}
bool Decoder::beginCallback(ReadByte reader,void* context,uint16_t size){reset();reader_=reader;context_=context;length_=size;if(!reader)return fail(READ_FAILURE);return header();}
bool Decoder::header(){
 if(length_<13)return fail(BAD_HEADER);
 if(readAt(0)!='L'||readAt(1)!='G')return fail(BAD_HEADER);
 profile_=readAt(2);const uint8_t mode=profile_&127;
 if(mode!=4&&mode!=6)return fail(BAD_HEADER);
 if(readWord(3)!=8000)return fail(BAD_HEADER);
 sampleCount_=remaining_=readWord(5);pre_=readWord(7);bright_=readWord(9);
 if(!remaining_||remaining_>64000||pre_>16384||bright_>11469||readWord(11)!=length_-13)return fail(BAD_HEADER);
 cursor_=13;return !error_;
}
uint16_t Decoder::bits(uint8_t count){
 uint16_t value=0;uint8_t used=0;
 while(count&&!error_){
  if(!bitsLeft_){bitBuffer_=readAt(cursor_);if(error_)break;++cursor_;bitsLeft_=8;}
  const uint8_t take=count<bitsLeft_?count:bitsLeft_;
  const uint16_t mask=((uint16_t)1<<take)-1;
  value|=(uint16_t)(bitBuffer_&mask)<<used;
  bitBuffer_>>=take;bitsLeft_-=take;used+=take;count-=take;
 }
 return value;
}
int16_t Decoder::signedBits(uint8_t count){
 const uint16_t value=bits(count);
 return (value&((uint16_t)1<<(count-1)))?(int16_t)((int32_t)value-((int32_t)1<<count)):(int16_t)value;
}
uint16_t Decoder::duration(){
 uint8_t zeros=0;
 while(!error_&&!bits(1))if(++zeros>8){fail(BAD_RUN);return 0;}
 if(error_)return 0;
 const uint16_t run=((uint16_t)1<<zeros)+bits(zeros);
 const uint16_t blocks=(remaining_+159u)/160u;
 if(!run||run>400||run>blocks){fail(BAD_RUN);return 0;}
 return run;
}
bool Decoder::anchor(){
 copy10(target_,base_);
 if(!bits(1))return !error_;
 const uint8_t plan=bits(2);uint8_t start=0;
 while(start<10&&!error_){
  uint8_t length=plan==0?10:plan==1?5:plan==2?2:(uint8_t)(bits(4)+1);
  if(length>10-start)return fail(BAD_ANCHOR);
  const uint8_t code=bits(3);
  if(code==7)return fail(BAD_ANCHOR);
  if(code==6){start+=length;continue;}
  if(code==5){for(uint8_t i=0;i<length;++i){int16_t value=signedBits(16);if(value==INT16_MIN)return fail(COEFFICIENT_RANGE);target_[start+i]=value;}}
  else {
   const uint8_t width=4+2*code,exponent=bits(4);
   for(uint8_t i=0;i<length;++i){
    const int16_t mantissa=signedBits(width);
    const int32_t value=(int32_t)base_[start+i]+(int32_t)mantissa*((int32_t)1<<exponent);
    if(value< -32767L||value>32767L)return fail(COEFFICIENT_RANGE);
    target_[start+i]=(int16_t)value;
   }
  }
  start+=length;
 }
 return !error_;
}
bool Decoder::scale(){
 if(!scaleRun_){
  scaleMode_=bits(2);
  if(scaleMode_==0){step_=stepForScale(bits(5));scaleRun_=1;}
  else if(scaleMode_==1){step_=stepForScale(bits(5));scaleRun_=duration();}
  else if(scaleMode_==2){
   logQ8_=logStart(bits(5));logSlope_=signedBits(12);scaleRun_=duration();
   const int32_t end=(int32_t)logQ8_+(int32_t)(scaleRun_?scaleRun_-1:0)*logSlope_;
   if(logQ8_<0||end<0||end>3071)return fail(BAD_CURVE);
  }else scaleRun_=duration();
 }
 if(error_)return false;
 if(scaleMode_==2){step_=logToStep(logQ8_);if(scaleRun_>1)logQ8_+=logSlope_;}
 else if(scaleMode_==3)step_=stepForScale(bits(5));
 --scaleRun_;return !error_;
}
void Decoder::literalPitch(){gain_=bits(3)*2;lag_=gain_?(uint8_t)(bits(7)+18):18;}
bool Decoder::pitch(){
 if(!pitchRun_){
  pitchMode_=bits(2);
  if(pitchMode_==0){literalPitch();pitchRun_=1;}
  else if(pitchMode_==1){literalPitch();pitchRun_=duration();}
  else if(pitchMode_==2){
   gain_=bits(3)*2;lag_=bits(7)+18;pitchSlope_=(int8_t)signedBits(8);pitchRun_=duration();
   const int32_t end=(int32_t)lag_+(int32_t)(pitchRun_?pitchRun_-1:0)*pitchSlope_;
   if(!gain_||end<18||end>145)return fail(BAD_CURVE);
  }else pitchRun_=duration();
 }else if(pitchMode_==2)lag_=(uint8_t)((int16_t)lag_+pitchSlope_);
 if(error_)return false;
 if(pitchMode_==3)literalPitch();
 --pitchRun_;return !error_;
}
bool Decoder::packet(){
 if((profile_&127)==4){
  for(uint8_t i=0;i<2;++i){const uint8_t code=bits(4);pulsePosition_[i]=code+(code+2)/4;pulseAmplitude_[i]=bits(1)?8:-8;}
 }else {
  const uint8_t low=bits(4),high=bits(5);if(high>=25)return fail(BAD_PULSE);
  const uint8_t packed=romByte(highCoordinates+high);
  pulsePosition_[0]=(low&3)|(packed&28);pulsePosition_[1]=(low>>2)|((packed>>3)&28);
  pulseAmplitude_[0]=(int8_t)signedBits(4);pulseAmplitude_[1]=(int8_t)signedBits(4);
 }
 extraPosition_=255;extraAmplitude_=0;
 if((profile_&128)&&bits(1)){extraPosition_=bits(6);extraAmplitude_=(int8_t)signedBits(4);if(extraPosition_>=40)return fail(BAD_PULSE);}
 return !error_;
}
bool Decoder::prepare(){
 if(subframe_==0){
  copy10(base_,target_);
  const bool changed=bits(1)!=0;
  if(!changed&&firstFrame_)return fail(BAD_ANCHOR);
  dynamicFrame_=changed&&!firstFrame_;
  if(changed&&!anchor())return false;
  if(firstFrame_||!changed)copy10(a_,target_);
  firstFrame_=false;
 }else if(subframe_==4&&dynamicFrame_){copy10(base_,target_);if(!anchor())return false;}
 if(dynamicFrame_&&subframe_<8){
  const uint8_t t=(subframe_&3)*2+1;
  for(uint8_t i=0;i<10;++i)a_[i]=lpx4LpcInterpolate<LPX4_USE_AVR_NOMUL_ASM>(base_[i],target_[i],t,3);
 }else if(subframe_==8)copy10(a_,target_);
 if(!(subframe_&7)){if(!scale()||!pitch())return false;}
 if(!(subframe_&1)&&!packet())return false;
 return !error_;
}
bool Decoder::sample(int16_t& q14){
 if(error_||!remaining_)return false;
 if(!subPos_&&!prepare())return false;
 int16_t q=lpx4PitchQ4(excitation_[(uint8_t)(ringCursor_-lag_)],gain_,LPX4_USE_AVR_NOMUL_ASM);
 const uint8_t pair=subframe_&1;
 if(subPos_==pulsePosition_[pair])q+=pulseAmplitude_[pair];
 if((uint8_t)(subPos_+(pair?20:0))==extraPosition_)q+=extraAmplitude_;
 if(q< -32)q=-32;else if(q>31)q=31;
 excitation_[ringCursor_++]=(int8_t)q;
 const int32_t excitation=lpx4Mul8xU16((int8_t)q,step_);
 int16_t predicted;
#if LPX4_USE_AVR_ASM && LPX4_COMPACT_VERSION==9 && LPX4_AVR_DOT_UNROLL==9
 constexpr size_t offset=offsetof(Decoder,history_)-offsetof(Decoder,subPos_);
 static_assert(offset<=63,"LG1 circular history exceeds AVR displacement");
 // The production circular leaf accepts Q4 excitation; other paths below
 // explicitly select unscaled excitation through the template argument.
 predicted=lpx4SynthesisCircularQ12<offset>(excitation*16L,a_,&subPos_);
#else
 predicted=lpx4Clip15From24<LPX4_USE_AVR_NOMUL_ASM>(lpx4SynthesisQ12<false,false,false,true>(excitation,a_,history_));
 history_[0]=predicted;
#endif
 q14=lpx4ClipQ14(lpx4PostfilterPair<offsetof(Decoder,previousDeemphasis_)-offsetof(Decoder,pre_)>(predicted,reinterpret_cast<uint8_t*>(&pre_)));
 --remaining_;if(++subPos_==20){subPos_=0;if(++subframe_==16)subframe_=0;}
 // Fully validate the final stored packet even when its second pulse is unplayed.
 if(!remaining_&&(cursor_!=length_||bitBuffer_))return fail(TRAILING_DATA);
 return true;
}
bool Decoder::nextQ14(int16_t& out){return sample(out);}
bool Decoder::nextS16(int16_t& out){int16_t q;if(!sample(q))return false;const int32_t value=(int32_t)q*2;out=value>32767?32767:(int16_t)value;return true;}
bool Decoder::next(uint8_t& out){int16_t q;if(!sample(q))return false;out=lpx4PwmQ14(q,130);return true;}
}
