#include "Lpx3AvrCore.h"
#ifdef __AVR__
#include <avr/pgmspace.h>
#define LP_READ_U16(ptr) pgm_read_word((ptr))
#define LP_PROGMEM PROGMEM
#else
#define LP_READ_U16(ptr) (*(ptr))
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

Lpx3AvrCore::Lpx3AvrCore(): reader_(0),context_(0),bytes_(0),cursor_(0),
    sampleCount_(0),position_(0),sampleRate_(0),preQ14_(0),brightQ14_(0),
    prevDeemph_(0),prevBright_(0),framePos_(0),blockPos_(0),subPos_(0),subIndex_(0),
    coeffScale_(0),coeffBits_(8),isLsf_(0),mode_(0),blockScale_(0),bitBuffer_(0),bitsLeft_(0),
    error_(NONE),initializedFrame_(false) {
#ifdef LPX3_COST_INSTRUMENT
    lsfConverts_=0;
#endif
#ifdef LPX3_FAST_LPC_INTERP
    lsfCached_=false;
#endif
    for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i]=a_[i]=hist_[i]=0,previousQuant_[i]=0;
}

int16_t Lpx3AvrCore::clamp(int32_t v,int16_t low,int16_t high){
    return v<low?low:(v>high?high:(int16_t)v);
}
int16_t Lpx3AvrCore::q12(int16_t value,uint8_t scale){
    if(!scale)return 0;
    const int32_t n=(int32_t)value*4096L;
    // C++ signed truncation toward zero, same on PC and AVR
    return clamp(n/scale,-32767,32767);
}
uint8_t Lpx3AvrCore::readByte(){
    if(error_)return 0;
    if(cursor_>=bytes_){error_=END_OF_ROM;return 0;}
    return reader_(context_,cursor_++);
}
uint16_t Lpx3AvrCore::read16(){
    const uint16_t lo=readByte();return (uint16_t)(lo|((uint16_t)readByte()<<8));
}
uint32_t Lpx3AvrCore::read32(){
    const uint32_t lo=read16();return lo|((uint32_t)read16()<<16);
}
bool Lpx3AvrCore::begin(ReadByte read,void* ctx,uint16_t bytes){
    // state reinitialization without assigning objects (small AVR stack)
    reader_=read;context_=ctx;bytes_=bytes;cursor_=0;error_=NONE;
    initializedFrame_=false;position_=0;framePos_=blockPos_=subPos_=subIndex_=0;
#ifdef LPX3_COST_INSTRUMENT
    lsfConverts_=0;
#endif
#ifdef LPX3_FAST_LPC_INTERP
    lsfCached_=false;
#endif
    prevDeemph_=prevBright_=0;mode_=blockScale_=bitBuffer_=bitsLeft_=0;coeffScale_=0;
    for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i]=a_[i]=hist_[i]=0,previousQuant_[i]=0;
    if(!read || bytes<20){error_=BAD_HEADER;return false;}
    if(readByte()!='L'||readByte()!='3'||readByte()!='A'||readByte()!='V'){
        error_=BAD_HEADER;return false;
    }
    if(readByte()!=1){error_=UNSUPPORTED;return false;}
    const uint8_t flags=readByte();
    if(flags>3){error_=UNSUPPORTED;return false;}
    coeffBits_=(flags&1)?10:8;isLsf_=(flags&2)?1:0;
    sampleRate_=read16();sampleCount_=read32();preQ14_=read16();brightQ14_=read16();
    const uint16_t frame=read16(),block=read16();
    if(error_||sampleRate_!=8000||!sampleCount_||frame!=160||block!=80||
       preQ14_>16384||brightQ14_>11469){error_=BAD_HEADER;return false;}
    return true;
}
bool Lpx3AvrCore::readFrame(){
    for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i];
    const uint8_t tag=readByte();uint8_t scale=coeffScale_;
    int16_t values[10];
    if(tag==0){
        if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
        return !error_;
    }
    if(tag==1 && coeffBits_==8){
        if(!isLsf_)scale=readByte();
        for(uint8_t i=0;i<10;i++)values[i]=isLsf_?(uint8_t)readByte():(int8_t)readByte();
    }else if(tag==5 && coeffBits_==10){
        if(!isLsf_)scale=readByte();
        uint32_t acc=0;uint8_t avail=0;
        for(uint8_t i=0;i<10;i++){
            while(avail<10){
                acc|=((uint32_t)readByte())<<avail;avail+=8;
            }
            int16_t value=(int16_t)(acc&1023);acc>>=10;avail-=10;
            if(!isLsf_ && value>=512)value-=1024;
            values[i]=value;
        }
    }else if((tag==2 && coeffBits_==8)||(tag==7 && coeffBits_==10)){
        if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
        for(uint8_t j=0;j<5;j++){
            const uint8_t pair=readByte();
            int8_t low=(int8_t)(pair&15), high=(int8_t)((pair>>4)&15);
            if(low>=8)low-=16;
            if(high>=8)high-=16;
            values[2*j]=previousQuant_[2*j]+low;
            values[2*j+1]=previousQuant_[2*j+1]+high;
        }
    }else if((tag==3 && coeffBits_==8)||(tag==6 && coeffBits_==10)){
        if(!initializedFrame_){error_=CORRUPT_STREAM;return false;}
        for(uint8_t i=0;i<10;i++)values[i]=previousQuant_[i]+(int8_t)readByte();
    }else {error_=CORRUPT_STREAM;return false;}
    if(isLsf_)scale=1;
    if(error_||!scale){error_=CORRUPT_STREAM;return false;}
    const int16_t limit=isLsf_?((1<<coeffBits_)-1):(coeffBits_==8?127:511);
    for(uint8_t i=0;i<10;i++){
        if(values[i]<(isLsf_?0:-limit)||values[i]>limit){error_=CORRUPT_STREAM;return false;}
        previousQuant_[i]=values[i];
        cur_[i]=isLsf_?values[i]:q12(values[i],scale);
    }
    if(!initializedFrame_)for(uint8_t i=0;i<10;i++)prev_[i]=cur_[i];
    initializedFrame_=true;coeffScale_=scale;
    return true;
}

bool Lpx3AvrCore::readBlock(){
    mode_=readByte();blockScale_=readByte();bitBuffer_=bitsLeft_=0;
    if(mode_!=0 && mode_!=2 && mode_!=3 && mode_!=4 && mode_!=5 && mode_!=6 && mode_!=0x83){error_=CORRUPT_STREAM;}
    return !error_;
}
uint8_t Lpx3AvrCore::rawBit(){
    if(!bitsLeft_){bitBuffer_=readByte();bitsLeft_=8;}
    const uint8_t bit=bitBuffer_&1;
    bitBuffer_>>=1;--bitsLeft_;return bit;
}
uint8_t Lpx3AvrCore::huffBit(){
    if(!bitsLeft_){bitBuffer_=readByte();bitsLeft_=8;}
    const uint8_t bit=(bitBuffer_>>7)&1;
    bitBuffer_<<=1;--bitsLeft_;return bit;
}
bool Lpx3AvrCore::decodeCode(int8_t& q){
    if(mode_==0){q=0;return true;}
    if(mode_==0x83){
        // exact tree: 00=>3, 011=>2, 010=>6, 10=>4,
        // 111=>5, 1101=>7, 11000=>0, 11001=>1
        if(!huffBit()){
            if(!huffBit())q=3;
            else q=huffBit()?2:6;
        }else if(!huffBit())q=4;
        else if(huffBit())q=5;
        else if(huffBit())q=7;
        else q=huffBit()?1:0;
    }else{
        uint8_t val=0;
        for(uint8_t bit=0;bit<mode_;bit++)val|=rawBit()<<bit;
        q=(int8_t)val-(1<<(mode_-1));
        return !error_;
    }
    q=(int8_t)q-4;return !error_;
}
void Lpx3AvrCore::interpolate(uint8_t sub){
    if(isLsf_){interpolateLsf(sub);return;}
    const int16_t t=(int16_t)(sub*2+1); // midpoint of 8 subframes, denominator 16
    for(uint8_t i=0;i<10;i++){
        const int32_t d=(int32_t)cur_[i]-prev_[i];
        a_[i]=clamp((int32_t)prev_[i]+(d*t)/16,-32767,32767);
    }
}
// Guard the 32x16 product on pathological/invalid LPX3 LSF vectors.
// Normal spectra take the single-multiply fast path; split product only if
// absolute polynomial coefficient would overflow signed int32 when *8192.
static inline int32_t polyMulQ12(int32_t v,int16_t c){
    if(v<=250000L && v>=-250000L)return (v*c)>>12;
    const int32_t hi=v/16, rem=v-hi*16;
    return ((hi*c)>>8)+((rem*c)>>12);
}
// LSF->LPC polynomial. Independent Q12 multiplication (no floats/trig in AVR).
void Lpx3AvrCore::polyFactor(int32_t* coefficients,int16_t c,uint8_t n){
    for(uint8_t i=0;i<n+2;i++)polyTmp_[i]=0;
    for(uint8_t i=0;i<n;i++){
        polyTmp_[i]+=coefficients[i];
        polyTmp_[i+1]+=polyMulQ12(coefficients[i],c);
        polyTmp_[i+2]+=coefficients[i];
    }
    for(uint8_t i=0;i<n+2;i++)coefficients[i]=polyTmp_[i];
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
void Lpx3AvrCore::convertLsfAt(uint8_t t,int16_t* out){
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
            const uint16_t norm=(uint16_t)((weighted*(coeffBits_==8?16:4))>>4);
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
void Lpx3AvrCore::interpolateLsf(uint8_t sub){
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

bool Lpx3AvrCore::next(uint8_t& pcm){
    if(error_||position_>=sampleCount_)return false;
    if(framePos_==0&&!readFrame())return false;
    if(blockPos_==0&&!readBlock())return false;
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
    int16_t duty=(int16_t)(128+((int32_t)b*127)/16384);
    pcm=(uint8_t)clamp(duty,0,255);
    ++position_;++framePos_;++blockPos_;++subPos_;
    if(subPos_==20){subPos_=0;++subIndex_;}
    if(blockPos_==80)blockPos_=0;
    if(framePos_==160){framePos_=0;subIndex_=0;}
    return true;
}
