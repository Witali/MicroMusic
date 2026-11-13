// Independent full convolution and ROM-table oracle for SRAM512 conversion.
// Exercise every ring cursor; no word-pointer casts into byte storage.
#define private public
#include "Lpx4HybridCore.cpp"
#include <stdio.h>

static const int16_t originalCosine[257]={
#include "cos_table.inc"
};
static int32_t floorDivide(int64_t value,uint8_t bits){
    const int64_t divisor=1LL<<bits;
    return (int32_t)(value>=0?value/divisor:-((-value+divisor-1)/divisor));
}
static int32_t product(int32_t value,int16_t coefficient){
    if(value>=-250000 && value<=250000)
        return floorDivide((int64_t)value*coefficient,12);
    const int32_t high=value/16;
    return floorDivide((int64_t)high*coefficient,8)+
           floorDivide((int64_t)(value-high*16)*coefficient,12);
}
static void convolve(int32_t* values,uint8_t degree,int16_t coefficient){
    int32_t next[12]={};
    for(uint8_t i=0;i<=degree+2;++i){
        if(i<=degree)next[i]+=values[i];
        if(i && i-1<=degree)next[i]+=product(values[i-1],coefficient);
        if(i>=2 && i-2<=degree)next[i]+=values[i-2];
    }
    memcpy(values,next,sizeof(next));
}
static void reference(const Lpx4HybridCore& core,uint8_t profile,uint8_t t,int16_t* out){
    int32_t p[12]={4096,4096},q[12]={4096,-4096};
    for(uint8_t i=0;i<10;++i){
        const int scale=(profile&2)?8:16;
        const int previous=(2*core.prev_[i]-1)*scale;
        const int current=(2*core.cur_[i]-1)*scale;
        const unsigned phase=(previous*16+(current-previous)*t)/4;
        const unsigned index=phase/16,fraction=phase%16;
        const int16_t cosine=(int16_t)(originalCosine[index]+
            floorDivide((int64_t)(originalCosine[index+1]-originalCosine[index])*fraction,4));
        convolve(i&1?q:p,(i&254)+1,(int16_t)-cosine);
    }
    for(uint8_t i=0;i<10;++i){
        const int32_t value=(p[i+1]+q[i+1])/2;
        out[i]=(int16_t)(value<-32767?-32767:value>32767?32767:value);
    }
}
static uint32_t state=20261110UL;
static uint8_t randomByte(){state=state*1664525UL+1013904223UL;return state>>24;}
static void spectrum(uint8_t* output,uint8_t bins,uint8_t trial){
    for(uint8_t i=0;i<10;++i){
        if(trial<4)output[i]=(trial&1)?bins-i:i+1;
        else if(trial<8)output[i]=(trial&1)?bins:1;
        else output[i]=(randomByte()%bins)+1;
    }
    // Also probe repeated/reversed LSF values in the helper's internal domain;
    // no stream parser is bypassed in the separate playback checks.
    if(trial>=8){
        for(uint8_t i=1;i<10;++i){
            uint8_t at=i,value=output[i];
            while(at && output[at-1]>value){output[at]=output[at-1];--at;}
            output[at]=value;
        }
    }
}
int main(){
    Lpx4HybridCore core;uint32_t conversions=0;
    const uint8_t profiles[]={4,6,15};
    for(uint8_t profile:profiles){
        core.speechProfile_=profile;
        const uint8_t bins=(profile&2)?64:32;
        for(uint8_t trial=0;trial<48;++trial){
            spectrum(core.prev_,bins,trial);
            spectrum(core.cur_,bins,(uint8_t)(trial^3));
            for(uint8_t t=0;t<=16;t+=16/LPX3_LPC_SEGMENTS){
                int16_t expected[10];reference(core,profile,t,expected);
                for(unsigned cursor=0;cursor<256;++cursor){
                    core.ringCursor_=(uint8_t)cursor;
                    for(unsigned i=0;i<256;++i)core.ringQ_[i]=(int8_t)(i*13+trial);
                    int8_t original[256];memcpy(original,core.ringQ_,sizeof original);
                    int16_t actual[10];core.convertLsfAt(t,actual);
                    if(memcmp(actual,expected,sizeof actual))return 1;
                    if(core.ringCursor_!=cursor)return 2;
                    for(unsigned lag=1;lag<=145;++lag){
                        const uint8_t slot=(uint8_t)(cursor-lag);
                        if(core.ringQ_[slot]!=original[slot])return 3;
                    }
                    ++conversions;
                }
            }
        }
    }
    printf("%lu conversions exact; all 256 cursors preserve 145 live slots\n",
           (unsigned long)conversions);
}
