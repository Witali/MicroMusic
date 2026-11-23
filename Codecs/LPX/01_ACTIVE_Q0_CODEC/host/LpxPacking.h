#pragma once
#include "LpxAdaptive.h"

namespace lpx {
// One bit cursor and previous spectrum across all input windows. drain() emits
// only completed bytes; finish() pads once at the actual EOF.
class V9PacketWriter {
    std::vector<uint8_t> pending;
    Spectrum previous={};
    bool hasPrevious=false,enhanced,finished=false,partialFrame=false;
    int profile=0,used=0;
    uint8_t partial=0;
    uint64_t written=0,spectral=0,frames=0;
public:
    explicit V9PacketWriter(bool extraPulses):enhanced(extraPulses) {}
    void put(int value,int width);
    void rice(int value,int order,int width);
    bool append(const Stream& stream);
    std::vector<uint8_t> drain();
    std::vector<uint8_t> finish();
    uint64_t bits() const { return written; }
    uint64_t spectrumBits() const { return spectral; }
    uint64_t frameCount() const { return frames; }
};
std::vector<uint8_t> v9Header(uint32_t samples,int profile,int rate,int pre,
                            int bright,bool extraPulses,uint32_t payloadBytes);
}
