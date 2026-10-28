// All valid cached states, next byte, short ROM lengths and a second refill.
#include <stdint.h>
#include <stdio.h>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "Lpx4HybridCore.cpp"
int main(){
    uint32_t cases=0;
    for(uint8_t available=0;available<=8;available++)
    for(uint16_t cached=0;cached<(1U<<available);cached++)
    for(uint16_t next=0;next<256;next++)
    for(uint8_t length=0;length<=2;length++)for(uint8_t second=0;second<2;second++){
        uint8_t bytes[2]={(uint8_t)next,(uint8_t)(second?~next:0)};
        Lpx4HybridCore actual;actual.data_=bytes;actual.bytes_=length;
#if !LPX4_ROM_POINTER
 actual.cursor_=0;
#endif

        actual.bitBuffer_=cached;actual.bitsLeft_=available;
        Lpx4HybridCore reference=actual;
        uint8_t high=0,expected=0;bool expectedOk=true;
        while(!reference.readOne()){
            if(reference.error_||++expected>8){reference.error_=Lpx4HybridCore::CORRUPT_STREAM;expectedOk=false;break;}
        }
        if(actual.readUnary8(high)!=expectedOk || high!=expected)return 1;
#if !LPX4_ROM_POINTER
        if(actual.cursor_!=reference.cursor_)return 4;
#endif
        if(actual.error_!=reference.error_ || actual.data_!=reference.data_ || actual.bytes_!=reference.bytes_ ||
            actual.bitBuffer_!=reference.bitBuffer_ || actual.bitsLeft_!=reference.bitsLeft_)return 2;
#ifdef LPX3_COST_INSTRUMENT
        if(actual.bitCalls_!=reference.bitCalls_ || actual.romByteCalls_!=reference.romByteCalls_)return 3;
#endif
        ++cases;
    }
    printf("%lu unary states\n",(unsigned long)cases);
}
