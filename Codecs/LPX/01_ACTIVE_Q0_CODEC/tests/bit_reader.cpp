// Internal reader oracle: all byte values, offsets, widths, refill and EOF.
#include <stdint.h>
#include <stdio.h>
#define private public
#include "Lpx4HybridCore.h"
#undef private
#include "../src/Lpx4HybridCore.cpp"
int main(){
    uint32_t cases=0;
    for(uint16_t a=0;a<256;a++)for(uint16_t b=0;b<256;b++)
    for(uint8_t offset=0;offset<8;offset++)for(uint8_t width=0;width<=8;width++){
        uint8_t bytes[3]={(uint8_t)a,(uint8_t)b,0xa5};
        Lpx4HybridCore d;d.data_=bytes;d.bytes_=3;
#if !LPX4_ROM_POINTER
 d.cursor_=0;
#endif

        d.bitBuffer_=0;d.bitsLeft_=0;
        for(uint8_t i=0;i<offset;i++)if(d.readOne()!=((a>>i)&1))return 1;
        uint16_t word=a|(b<<8);
        uint8_t expected=(word>>offset)&((1u<<width)-1);
        if(d.readBits(width)!=expected || d.error())return 2;
        // A following read must observe the exact residual state.
        uint32_t all=(uint32_t)word|0xa50000UL;
        if(d.readBits(8)!=(uint8_t)(all>>(offset+width)))return 3;
        ++cases;
    }
    Lpx4HybridCore d;uint8_t byte=0x5a;
    d.data_=&byte;d.bytes_=1;
#if !LPX4_ROM_POINTER
 d.cursor_=0;
#endif
d.bitsLeft_=0;d.bitBuffer_=0;
    if(d.readBits(8)!=0x5a||d.error())return 4;
    d.readOne();if(d.error()!=Lpx4HybridCore::END_OF_ROM)return 5;
    printf("%lu reader cases\n",(unsigned long)cases);
}
