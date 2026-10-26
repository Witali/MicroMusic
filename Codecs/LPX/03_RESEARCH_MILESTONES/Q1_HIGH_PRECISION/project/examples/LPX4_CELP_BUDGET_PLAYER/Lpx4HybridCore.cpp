#include "Lpx4HybridCore.h"
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
#define LPX3_FAST_LPC_INTERP 1
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
// Signed 16x16 -> 32 using four native 8x8 products.
// Avoids repeated 32-bit software multiplier calls in the 8kHz sample loop.
// Sum is modulo 2^32, matching two's complement signed product.
static inline int32_t mul16x16(int16_t x,int16_t y){
    const uint8_t xl=(uint8_t)x,yl=(uint8_t)y;
    const int8_t xh=(int8_t)(((uint16_t)x)>>8),yh=(int8_t)(((uint16_t)y)>>8);
    const uint16_t ll=(uint16_t)xl*yl;
    const int16_t hl=(int16_t)xh*yl,lh=(int16_t)yh*xl;
    const int16_t hh=(int16_t)xh*yh;
    const uint32_t z=(uint32_t)ll+((uint32_t)(int32_t)hl<<8)+
       ((uint32_t)(int32_t)lh<<8)+((uint32_t)(int32_t)hh<<16);
    return (int32_t)z;
}

static const int16_t LP_PROGMEM cosineQ13[257]={
#include "cos_table.inc"
};
static const uint16_t LP_PROGMEM stepQ14[256]={
#include "scale_table.inc"
};


Lpx4HybridCore::Lpx4HybridCore(): data_(0),bytes_(0),cursor_(0),sampleCount_(0),position_(0),
 sampleRate_(0),preQ14_(0),brightQ14_(0),prevDeemph_(0),prevBright_(0),
 framePos_(0),blockPos_(0),subPos_(0),subIndex_(0),mode_(0),blockScale_(0),
 bitBuffer_(0),bitsLeft_(0),riceK_(0),subType_(0),lag_(0),gain_(0),ringCursor_(0),
#if LPX4_ALLOW_SPARSE
 pulseCount_(0),pulseIndex_(0),
#endif
 error_(NONE),initializedFrame_(false) {
#ifdef LPX3_COST_INSTRUMENT
 lsfConverts_=bitCalls_=romByteCalls_=0;
#endif
 lsfCached_=false;
 for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i]=a_[i]=hist_[i]=previousQuant_[i]=0;
 for(uint16_t i=0;i<256;i++)ringQ_[i]=0;
}
int16_t Lpx4HybridCore::clamp(int32_t n,int16_t low,int16_t high){
 return n<low?low:(n>high?high:(int16_t)n);
}
uint8_t Lpx4HybridCore::readByte(){
#ifdef LPX3_COST_INSTRUMENT
 ++romByteCalls_;
#endif
 if(error_)return 0;
 if(cursor_>=bytes_){error_=END_OF_ROM;return 0;}
 return LP_READ_U8(data_+cursor_++);
}
uint16_t Lpx4HybridCore::read16(){
 const uint16_t low=readByte();return (uint16_t)(low | (uint16_t)readByte()<<8);
}
uint32_t Lpx4HybridCore::read32(){
 const uint32_t low=read16();return low|((uint32_t)read16()<<16);
}
bool Lpx4HybridCore::begin(const uint8_t* input,uint16_t size){
 data_=input;bytes_=size;cursor_=0;error_=NONE;initializedFrame_=false;
 position_=0;framePos_=blockPos_=subPos_=subIndex_=0;
 bitBuffer_=bitsLeft_=mode_=blockScale_=riceK_=0;
 subType_=lag_=gain_=ringCursor_=0;
#if LPX4_ALLOW_SPARSE
 pulseCount_=pulseIndex_=0;
#endif
 lsfCached_=false;prevDeemph_=prevBright_=0;
#ifdef LPX3_COST_INSTRUMENT
 lsfConverts_=bitCalls_=romByteCalls_=0;
#endif
 for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i]=a_[i]=hist_[i]=previousQuant_[i]=0;
 for(uint16_t i=0;i<256;i++)ringQ_[i]=0;
 if(!input||size<20){error_=BAD_HEADER;return false;}
 if(readByte()!='L'||readByte()!='4'||readByte()!='H'||readByte()!='Y'){
  error_=BAD_HEADER;return false;
 }
 const uint8_t version=readByte(),flags=readByte();
 if(version!=2||flags!=3){error_=UNSUPPORTED;return false;}
 sampleRate_=read16();sampleCount_=read32();preQ14_=read16();brightQ14_=read16();
 const uint16_t frames=read16(),blocks=read16();
 if(error_||sampleRate_!=8000||!sampleCount_||frames!=160||blocks!=80||
    preQ14_>16384||brightQ14_>11469){error_=BAD_HEADER;return false;}
 return true;
}
uint8_t Lpx4HybridCore::readOne(){
#ifdef LPX3_COST_INSTRUMENT
 ++bitCalls_;
#endif
 if(!bitsLeft_){bitBuffer_=readByte();bitsLeft_=8;}
 const uint8_t r=bitBuffer_&1;
 bitBuffer_>>=1;
 --bitsLeft_;
 return r;
}
uint8_t Lpx4HybridCore::readBits(uint8_t n){
#ifdef LPX3_COST_INSTRUMENT
 ++bitCalls_;
#endif
 uint16_t b=bitBuffer_;uint8_t avail=bitsLeft_;
 if(avail<n){b|=(uint16_t)readByte()<<avail;avail+=8;}
 const uint8_t out=(uint8_t)(b&((1u<<n)-1u));
 bitBuffer_=(uint8_t)(b>>n);bitsLeft_=avail-n;
 return out;
}
bool Lpx4HybridCore::readFrame(){
 for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i];
 if(!readOne()){
  if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
  return !error_;
 }
 int16_t v[10];
 if(!readOne()){
  // LSF10 absolute: 10 * exactly 10 bits (no pad to 13-byte frame).
  for(uint8_t i=0;i<10;i++)v[i]=(int16_t)(readBits(8)|((uint16_t)readBits(2)<<8));
 }else{
  if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
  const bool raw=readOne()!=0;
  for(uint8_t i=0;i<10;i++){
   int8_t d=0;
   if(raw)d=(int8_t)readBits(8);
   else {
    uint8_t z=0;
    while(!readOne()){
     if(error_||++z>7){error_=CORRUPT_STREAM;return false;}
    }
    const int8_t hi=(z&1)?-(int8_t)((z+1)>>1):(int8_t)(z>>1);
    const uint8_t lo=readOne()?readBits(5):0;
    d=(int8_t)((int16_t)hi*32+lo);
   }
   v[i]=previousQuant_[i]+d;
  }
 }
 if(error_)return false;
 for(uint8_t i=0;i<10;i++){
  if(v[i]<0||v[i]>1023){error_=CORRUPT_STREAM;return false;}
  previousQuant_[i]=v[i];cur_[i]=v[i];
 }
 if(!initializedFrame_)for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i];
 initializedFrame_=true;return true;
}
bool Lpx4HybridCore::readBlock(){
 mode_=readBits(3); // source bit depth, 0 or 2..6
 if(mode_!=0 && (mode_<2 || mode_>6)){error_=CORRUPT_STREAM;return false;}
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
 return !error_;
}
bool Lpx4HybridCore::readSubframe(){
 subType_=readBits(2);
#if LPX4_ALLOW_SPARSE
 pulseIndex_=pulseCount_=0;
#endif
 if(subType_==3){error_=CORRUPT_STREAM;return false;}
 if(subType_==0){
   riceK_=readBits(3);
   if(riceK_==7 && mode_!=3){error_=CORRUPT_STREAM;return false;}
 }else{
   lag_=(uint8_t)(18+readBits(7));
   gain_=readBits(5);
   if(lag_>145){error_=CORRUPT_STREAM;return false;}
   if(subType_==1)riceK_=readBits(3);
   else{
#if LPX4_ALLOW_SPARSE
     pulseCount_=readBits(4);
     if(pulseCount_>LPX4_MAX_PULSES){error_=CORRUPT_STREAM;return false;}
     const uint8_t remaining=(uint8_t)((sampleCount_-position_)>=40?40:(sampleCount_-position_));
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
}
int16_t Lpx4HybridCore::pitchPredict() const{
 const int16_t x=ringQ_[(uint8_t)(ringCursor_-lag_)];
 int16_t v=(int16_t)(((int16_t)gain_*x+8)>>4);
 if(!mode_)return 0;
 const int16_t lim=(int16_t)(1u<<(mode_-1));
 if(v < -lim)v=-lim;
 if(v >= lim)v=lim-1;
 return v;
}
bool Lpx4HybridCore::decodeCode(int8_t& q){
 int16_t decoded=0;
 if(subType_==0){
   if(!mode_)decoded=0;
   else if(riceK_==7){
     if(!readOne()){
       if(!readOne())decoded=-1;
       else decoded=readOne() ? -2 : 2;
     }else if(!readOne())decoded=0;
     else if(readOne())decoded=1;
     else if(!readOne())decoded=3;
     else decoded=readOne() ? -3 : -4;
   }else if(riceK_){
     uint8_t high=0;
     while(!readOne()){
       if(error_||++high>8){error_=CORRUPT_STREAM;return false;}
     }
     const uint16_t z=(uint16_t)((high<<riceK_)|readBits(riceK_));
     decoded=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
   }else decoded=(int16_t)readBits(mode_)-(int16_t)(1u<<(mode_-1));
 }else{
   decoded=pitchPredict();
   int16_t d=0;
   if(subType_==1){
     if(riceK_==7)d=(int8_t)readBits(8);
     else{
       uint8_t high=0;
       while(!readOne()){
         if(error_||++high>8){error_=CORRUPT_STREAM;return false;}
       }
       const uint16_t z=(uint16_t)((high<<riceK_) | (riceK_?readBits(riceK_):0));
       d=(z&1)?-(int16_t)((z+1)>>1):(int16_t)(z>>1);
     }
   }
#if LPX4_ALLOW_SPARSE
   else if(pulseIndex_<pulseCount_ && pulsePos_[pulseIndex_]==(blockPos_%40)){
       d=pulseAmp_[pulseIndex_++];
   }
#endif
   decoded+=d;
   if(subType_==2){
     if(!mode_)decoded=0;
     else{
       const int16_t lim=(int16_t)(1u<<(mode_-1));
       if(decoded < -lim)decoded=-lim;
       if(decoded >= lim)decoded=lim-1;
     }
   }
 }
 if(error_)return false;
 if(mode_){
   const int16_t lim=(int16_t)(1u<<(mode_-1));
   if(decoded < -lim || decoded >= lim){error_=CORRUPT_STREAM;return false;}
 }else if(decoded){error_=CORRUPT_STREAM;return false;}
 q=(int8_t)decoded;
 ringQ_[ringCursor_++]=q;
 return true;
}
void Lpx4HybridCore::interpolate(uint8_t sub){interpolateLsf(sub);}
// Guard the 32x16 product on pathological/invalid LPX3 LSF vectors.
// Normal spectra take the single-multiply fast path; split product only if
// absolute polynomial coefficient would overflow signed int32 when *8192.
static inline int32_t polyMulQ12(int32_t v,int16_t c){
    if(v<=250000L && v>=-250000L)return (v*c)>>12;
    const int32_t hi=v/16, rem=v-hi*16;
    return ((hi*c)>>8)+((rem*c)>>12);
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
    p[1]=polyMulQ12(p[0],c)+p[1];
}
#ifdef LPX3_FAST_LPC_INTERP
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
    const uint8_t coeffBits=10;
#ifdef LPX3_COST_INSTRUMENT
    ++lsfConverts_;
#endif
    polyP_[0]=polyQ_[0]=4096;
    polyP_[1]=4096;polyQ_[1]=-4096;
    uint8_t n=2;
    for(uint8_t i=0;i<10;i+=2){
        int16_t cc[2];
        for(uint8_t j=0;j<2;j++){
            const int32_t weighted=(int32_t)prev_[i+j]*(16-t)+(int32_t)cur_[i+j]*t;
            const uint16_t norm=(uint16_t)(weighted>>2);
            const uint8_t idx=(uint8_t)(norm>>4),frac=(uint8_t)(norm&15);
            const int16_t lo=(int16_t)LP_READ_U16(&cosineQ13[idx]);
            const int16_t hi=(int16_t)LP_READ_U16(&cosineQ13[(uint16_t)idx+1]);
            const int16_t cosQ13=(int16_t)(lo+(((int32_t)(hi-lo)*frac)>>4));
            cc[j]=(int16_t)(-cosQ13);
        }
        polyFactor(polyP_,cc[0],n);
        polyFactor(polyQ_,cc[1],n);
        n+=2;
    }
    for(uint8_t i=0;i<10;i++)out[i]=clamp((polyP_[i+1]+polyQ_[i+1])/2,-32767,32767);
}
#endif
void Lpx4HybridCore::interpolateLsf(uint8_t sub){
#ifdef LPX3_FAST_LPC_INTERP
    // Segment width in t=0..16; at most one polynomial conversion per
    // 20-sample subframe after the initial frame (two at startup).
    const uint8_t width=(uint8_t)(16/LPX3_LPC_SEGMENTS);
    const uint8_t subframesPerSegment=(uint8_t)(8/LPX3_LPC_SEGMENTS);
    if(sub%subframesPerSegment==0){
        if(sub==0){
            if(lsfCached_){
                // Last endpoint of prior frame was this frame's old LSF.
                for(uint8_t i=0;i<10;i++)prevLpc_[i]=curLpc_[i];
            }else convertLsfAt(0,prevLpc_);
        }else{
            for(uint8_t i=0;i<10;i++)prevLpc_[i]=curLpc_[i];
        }
        const uint8_t anchor=(uint8_t)(((sub/subframesPerSegment)+1)*width);
        convertLsfAt(anchor,curLpc_);
        lsfCached_=true;
    }
    const uint8_t t=(uint8_t)(sub*2+1);
    const uint8_t localT=(uint8_t)(t%width);
    for(uint8_t i=0;i<10;i++){
        const int32_t d=(int32_t)curLpc_[i]-prevLpc_[i];
        a_[i]=clamp((int32_t)prevLpc_[i]+d*localT/width,-32767,32767);
    }
    return;
#else
#ifdef LPX3_COST_INSTRUMENT
    ++lsfConverts_;
#endif
    // Center of 8 subframes: t=(sub+0.5)/8.
    const uint8_t t=(uint8_t)(sub*2+1);
    polyP_[0]=polyQ_[0]=4096;
    polyP_[1]=4096;polyQ_[1]=-4096;
    uint8_t n=2;
    for(uint8_t i=0;i<10;i+=2){
        int16_t cc[2];
        for(uint8_t j=0;j<2;j++){
            int32_t weighted=(int32_t)prev_[i+j]*(16-t)+(int32_t)cur_[i+j]*t;
            // normalize encoded LSF (Q8/Q10) to Q12 without division.
            const uint16_t norm=(uint16_t)((weighted*(coeffBits_==8?16:4))>>4);
            const uint8_t idx=(uint8_t)(norm>>4),frac=(uint8_t)(norm&15);
            const int16_t lo=(int16_t)LP_READ_U16(&cosineQ13[idx]);
            const int16_t hi=(int16_t)LP_READ_U16(&cosineQ13[(uint16_t)idx+1]);
            const int16_t cosQ13=(int16_t)(lo+(((int32_t)(hi-lo)*frac)>>4));
            cc[j]=(int16_t)(-cosQ13); // -2cos(pi*lsf), Q12
        }
        polyFactor(polyP_,cc[0],n);
        polyFactor(polyQ_,cc[1],n);
        n+=2;
    }
    for(uint8_t i=0;i<10;i++){
        a_[i]=clamp((polyP_[i+1]+polyQ_[i+1])/2,-32767,32767);
    }
#endif
}

// On a normal AVR firmware compile the existing 8-bit path exactly as before.
// The 16-bit research path is enabled by host compilation, or optionally by
// -DLPX4_ENABLE_PCM16 on the AVR. No extra call or helper in standard AVR mode.
#if defined(__AVR__) && !defined(LPX4_ENABLE_PCM16)
bool Lpx4HybridCore::next(uint8_t& pcm){
#else
bool Lpx4HybridCore::nextCore(int16_t& postfilterQ14){
#endif
    if(error_||position_>=sampleCount_)return false;
    if(framePos_==0&&!readFrame())return false;
    if(blockPos_==0&&!readBlock())return false;
    if(blockPos_%40==0 && !readSubframe())return false;
    if(subPos_==0){
        interpolate(subIndex_);
#ifdef LPX3_BANDWIDTH_EXPAND_Q14
        // Bandwidth expansion a[k] *= gamma^(k+1), once per 20 samples.
        uint16_t weight=16384;
        for(uint8_t k=0;k<10;k++){
            weight=(uint16_t)(((int32_t)weight*LPX3_BANDWIDTH_EXPAND_Q14+8192)>>14);
            a_[k]=clamp(((int32_t)a_[k]*weight+8192)>>14,-32767,32767);
        }
#endif
    }
    int8_t q=0;if(!decodeCode(q))return false;
#ifdef LPX3_Q_DIAG
    lastQ_=q;
#endif
    const uint16_t step=LP_READ_U16(&stepQ14[blockScale_]);
    int32_t excitation=(int32_t)q*step, acc=0;
    for(uint8_t i=0;i<10;i++)acc+=(mul16x16(a_[i],hist_[i]))>>12;
    int16_t pred=clamp(excitation-acc,-32767,32767);
    for(uint8_t i=9;i>0;i--)hist_[i]=hist_[i-1];
    hist_[0]=pred;
    int16_t deemph=clamp((int32_t)pred+((mul16x16((int16_t)preQ14_,prevDeemph_))>>14),-32767,32767);
    prevDeemph_=deemph;
    int16_t clipped=clamp(deemph,-16384,16384);
    int16_t b=clamp((int32_t)clipped-((mul16x16((int16_t)brightQ14_,prevBright_))>>14),-16384,16384);
    prevBright_=clipped;
    // Preserve the signed post-deemphasis/post-brightness output BEFORE PWM.
    // This is the exact integer sample used by both optional 16-bit output
    // and legacy PWM conversion; no 8-bit quantization has happened yet.
#if defined(__AVR__) && !defined(LPX4_ENABLE_PCM16)
    // Original PWM transfer function for the existing ATmega328P firmware.
#if LPX4_PWM_ROUND
    const int32_t scaled=(int32_t)b*LPX4_PWM_GAIN+8192;
    int16_t duty=(int16_t)(128+(scaled>>14));
#else
    int16_t duty=(int16_t)(128+((int32_t)b*LPX4_PWM_GAIN)/16384);
#endif
    pcm=(uint8_t)clamp(duty,0,255);
#else
    postfilterQ14 = b;
#endif
    ++position_;++framePos_;++blockPos_;++subPos_;
    if(subPos_==20){subPos_=0;++subIndex_;}
    if(blockPos_==80)blockPos_=0;
    if(framePos_==160){framePos_=0;subIndex_=0;}
    return true;
}

// Legacy 8-bit output retained for unchanged AVR/Arduino playback.
#if !defined(__AVR__) || defined(LPX4_ENABLE_PCM16)
bool Lpx4HybridCore::next(uint8_t& pcm){
    int16_t b;
    if(!nextCore(b))return false;
#if LPX4_PWM_ROUND
    const int32_t scaled=(int32_t)b*LPX4_PWM_GAIN+8192;
    const int16_t duty=(int16_t)(128+(scaled>>14));
#else
    const int16_t duty=(int16_t)(128+((int32_t)b*LPX4_PWM_GAIN)/16384);
#endif
    pcm=(uint8_t)clamp(duty,0,255);
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
