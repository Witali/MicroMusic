// Host-only persistent binary transport around the unchanged native receiver.
// Never linked into firmware. All protocol integers are explicitly little-endian.
#include "Lpx4HybridCore.h"
#include <cstdio>
#include <cstdint>
#include <vector>

namespace {
constexpr uint32_t Hello=0x5348504c,Request=0x3144504c,Response=0x3152504c;
bool readExact(void* destination,size_t bytes) {
    auto* p=static_cast<uint8_t*>(destination);
    while(bytes) {size_t got=std::fread(p,1,bytes,stdin);if(!got)return false;p+=got;bytes-=got;}
    return true;
}
uint32_t word(const uint8_t* p) {
    return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);
}
bool put(uint32_t value) {
    const uint8_t p[]={uint8_t(value),uint8_t(value>>8),uint8_t(value>>16),uint8_t(value>>24)};
    return std::fwrite(p,1,4,stdout)==4;
}
}
int main() {
    for(uint32_t value:{Hello,1u,uint32_t(LPX4_COMPACT_ONLY),uint32_t(LPX4_COMPACT_VERSION),uint32_t(LPX4_FLOAT_SYNTHESIS)})
        if(!put(value))return 1;
    if(std::fflush(stdout))return 1;
    while(true) {
        uint8_t header[24];const int first=std::fgetc(stdin);
        if(first==EOF)return std::feof(stdin)?0:2;
        header[0]=uint8_t(first);if(!readExact(header+1,23))return 2;
        const uint32_t id=word(header+4),mode=word(header+8),bytes=word(header+12),expected=word(header+16);
        // A corrupt transport frame closes the process without oversized allocation.
        if(word(header)!=Request||word(header+20)||bytes>65535||expected>1000000)return 3;
        std::vector<uint8_t> input(bytes);if(bytes&&!readExact(input.data(),bytes))return 2;
        Lpx4HybridCore core;int32_t status=0;uint32_t got=0;
        std::vector<uint8_t> output;
        if(mode>1)status=-1;
        else if(bytes<20)status=-2;
        else if(!core.begin(input.data(),uint16_t(bytes))||core.samples()!=expected)status=-3;
        else {
            output.reserve(expected*(mode?2:1));
            while(got<expected) {
                if(mode) {
                    int16_t value;if(!core.nextS16(value))break;
                    output.push_back(uint8_t(value));output.push_back(uint8_t(uint16_t(value)>>8));
                } else {uint8_t value;if(!core.next(value))break;output.push_back(value);}
                ++got;
            }
            bool extra;
            if(mode){int16_t value;extra=core.nextS16(value);}else{uint8_t value;extra=core.next(value);}
            if(got!=expected||extra||core.error()||!core.finished())status=-4;
        }
        if(status)output.clear();
        const uint32_t meta[]={Response,id,uint32_t(status),got,core.samples(),core.sampleRate(),core.produced(),
            uint32_t(core.error()),uint32_t(core.finished()),uint32_t(output.size()),uint32_t(LPX4_COMPACT_ONLY),
            uint32_t(LPX4_COMPACT_VERSION),uint32_t(LPX4_FLOAT_SYNTHESIS)};
        for(uint32_t value:meta)if(!put(value))return 1;
        if(!output.empty()&&std::fwrite(output.data(),1,output.size(),stdout)!=output.size())return 1;
        if(std::fflush(stdout))return 1;
    }
}
