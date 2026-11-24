// Browser ABI for the portable LPX V9 / host-only V9 Long C backend.
#include "Lpx4HybridCore.h"
#include "LpxHostWorkspace.h"
#include <stdint.h>

static uint8_t* input;
static int16_t* output;
static uint32_t inputCapacity, outputCapacity;
static uint32_t sampleCount, sampleRate;
static Lpx4HybridCore incremental;
static uint32_t decodedCount;
static bool reading;

extern "C" {
int lpx_reserve(uint32_t bytes, uint32_t samples) {
    inputCapacity = outputCapacity = 0;
    if (bytes < 13 || bytes > kLpxMaxFileBytes || !samples || samples > kLpxMaxDecodedSamples) return 0;
    const uint64_t inputBytes=(uint64_t(bytes)+7)&~uint64_t(7);
    const uint64_t required=inputBytes+uint64_t(samples)*sizeof(int16_t);
    if(required>UINT32_MAX)return 0;
    uint8_t* memory = static_cast<uint8_t*>(reserveWorkspace(uint32_t(required)));
    if (!memory) return 0;
    input = memory; output = reinterpret_cast<int16_t*>(memory + uint32_t(inputBytes));
    inputCapacity = bytes; outputCapacity = samples;
    return 1;
}
uint8_t* lpx_input() { return input; }
int16_t* lpx_output() { return output; }
uint32_t lpx_samples() { return sampleCount; }
uint32_t lpx_rate() { return sampleRate; }
int lpx_decode_begin(uint32_t bytes){
    reading=false;sampleCount=sampleRate=decodedCount=0;
    if(bytes<13||bytes>inputCapacity||!incremental.beginWideV9(input,bytes))return -1;
    sampleCount=incremental.samples();sampleRate=incremental.sampleRate();reading=true;return 0;
}
int lpx_decode_read(uint32_t count){
    if(!reading||!count||count>outputCapacity||count>sampleCount-decodedCount)return -1;
    for(uint32_t i=0;i<count;++i)if(!incremental.nextS16(output[i])){reading=false;return -2;}
    decodedCount+=count;
    if(decodedCount==sampleCount){int16_t tail;reading=false;if(incremental.nextS16(tail)||incremental.error()||!incremental.finished())return -2;}
    return count;
}

// 0: success, -1: size/header, -2: payload (including strict final EOF).
int lpx_decode(uint32_t bytes) {
    sampleCount = sampleRate = 0;
    if (bytes < 13 || bytes > inputCapacity) return -1;
    Lpx4HybridCore core;
    if (!core.beginWideV9(input, bytes)) return -1;
    const uint32_t count = core.samples();
    if (!count || count > outputCapacity) return -1;
    uint32_t position = 0;
    while (position < count && core.nextS16(output[position])) ++position;
    int16_t tail;
    if (position != count || core.nextS16(tail) || core.error() || !core.finished()) return -2;
    sampleCount = count;
    sampleRate = core.sampleRate();
    return 0;
}
}
