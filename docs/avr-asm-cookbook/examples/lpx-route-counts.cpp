#include <stdint.h>
#include <stdio.h>
#include <fstream>
#include <iterator>
#include <vector>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
int main(int argc,char** argv){
    uint32_t counts[7]={0},pitchK[7]={0},zeroDelta[7]={0},cachedZeroK0=0,sparseExhausted=0;
    for(int file=1;file<argc;file++){
        std::ifstream in(argv[file],std::ios::binary);
        std::vector<uint8_t> blob((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
        Lpx4HybridCore d;if(!d.begin(blob.data(),blob.size()))return 2;
        int16_t value;
        while(d.nextS16(value)){
            unsigned slot=d.subType_==2?6:d.subType_==1?(d.riceK_==7?5:4):
                !d.mode_?0:!d.riceK_?1:d.riceK_==7?3:2;
            ++counts[slot];
            if(slot==4){
                ++pitchK[d.riceK_];
                int16_t predicted=((int16_t)d.gain_*d.ringQ_[(uint8_t)(d.ringCursor_-1-d.lag_)]+8)>>4;
                if(!d.mode_)predicted=0;
                else{
                    if(predicted<-(int16_t)d.quantLimit_)predicted=-(int16_t)d.quantLimit_;
                    if(predicted>=d.quantLimit_)predicted=d.quantLimit_-1;
                }
                const int8_t actual=d.ringQ_[(uint8_t)(d.ringCursor_-1)];
                if(actual==predicted){
                    ++zeroDelta[d.riceK_];
                    if(d.riceK_==0 && d.bitsLeft_<7)++cachedZeroK0;
                }
            }
            if(slot==6 && d.pulseIndex_>=d.pulseCount_){
                const uint8_t previousPos=(d.subPos_+((d.subIndex_&1)?20:0)+39)%40;
                const bool consumed=d.pulseIndex_ && d.pulsePos_[d.pulseIndex_-1]==previousPos;
                if(!consumed)++sparseExhausted;
            }
        }
        if(!d.finished())return 3;
    }
    printf("{\"zero_direct\":%lu,\"raw_direct\":%lu,\"rice_direct\":%lu,\"huffman\":%lu,\"pitch_rice\":%lu,\"pitch_literal\":%lu,\"sparse\":%lu,",
        (unsigned long)counts[0],(unsigned long)counts[1],(unsigned long)counts[2],(unsigned long)counts[3],
        (unsigned long)counts[4],(unsigned long)counts[5],(unsigned long)counts[6]);
    printf("\"cached_zero_pitch_k0\":%lu,\"sparse_exhausted_before_sample\":%lu,\"pitch_rice_by_k\":[",
        (unsigned long)cachedZeroK0,(unsigned long)sparseExhausted);
    for(unsigned k=0;k<7;k++)printf("%s%lu",k?",":"",(unsigned long)pitchK[k]);
    printf("],\"zero_delta_by_k\":[");
    for(unsigned k=0;k<7;k++)printf("%s%lu",k?",":"",(unsigned long)zeroDelta[k]);
    printf("]}\n");
}
