// Actual fast readers versus the original readOne decisions, including EOF
// and exact residual cursor/buffer/error state. No stream encoder is shared.
#include <stdint.h>
#include <stdio.h>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"

static bool same(const Lpx4HybridCore& a,const Lpx4HybridCore& b){
    if(a.cursor_!=b.cursor_ || a.bitBuffer_!=b.bitBuffer_ || a.bitsLeft_!=b.bitsLeft_ || a.error_!=b.error_)return false;
#ifdef LPX3_COST_INSTRUMENT
    if(a.bitCalls_!=b.bitCalls_ || a.romByteCalls_!=b.romByteCalls_)return false;
#endif
    return true;
}
static int8_t huffman(Lpx4HybridCore& d){
    if(!d.readOne()){
        if(!d.readOne())return -1;
        return d.readOne()?-2:2;
    }
    if(!d.readOne())return 0;
    if(d.readOne())return 1;
    if(!d.readOne())return 3;
    return d.readOne()?-3:-4;
}
static bool check(Lpx4HybridCore d){
    Lpx4HybridCore fast=d,slow=d;
    if(fast.readHuffman3()!=huffman(slow) || !same(fast,slow))return false;
    return true;
}
int main(){
    uint32_t cases=0;
    for(uint32_t word=0;word<65536;word++)for(uint8_t offset=0;offset<8;offset++){
        uint8_t bytes[2]={(uint8_t)word,(uint8_t)(word>>8)};
        Lpx4HybridCore d;d.data_=bytes;d.bytes_=2;
        for(uint8_t n=0;n<offset;n++)d.readOne();
        if(!check(d))return 1;
        ++cases;
    }
    // Every possible partial cached byte, followed by EOF, including an
    // already sticky error. The unused upper bits are zero by invariant.
    for(uint8_t available=0;available<=8;available++)for(uint16_t value=0;value<(1u<<available);value++){
        for(uint8_t error=0;error<=Lpx4HybridCore::END_OF_ROM;error++){
            Lpx4HybridCore d;d.bitsLeft_=available;d.bitBuffer_=value;
            d.bytes_=0;d.error_=(Lpx4HybridCore::Error)error;
            if(!check(d))return 2;
            ++cases;
        }
    }
    printf("%lu bit-code states exact\n",(unsigned long)cases);
}
