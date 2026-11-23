// Browser ABI for the portable LPX V9 / host-only V9 Long C backend.
#include "Lpx4HybridCore.h"
#include "LpxHostWorkspace.h"
#include <stdint.h>

static uint8_t* input;
static int16_t* output;
static uint32_t inputCapacity, outputCapacity;
static uint32_t sampleCount, sampleRate;

extern "C" {
int lpx_reserve(uint32_t bytes, uint32_t samples) {
    inputCapacity = outputCapacity = 0;
    if (bytes < 13 || bytes > kLpxMaxFileBytes || !samples || samples > kLpxMaxSamples) return 0;
    uint8_t* memory = static_cast<uint8_t*>(reserveWorkspace(((bytes + 7) & ~7u) + samples * 2));
    if (!memory) return 0;
    input = memory; output = reinterpret_cast<int16_t*>(memory + ((bytes + 7) & ~7u));
    inputCapacity = bytes; outputCapacity = samples;
    return 1;
}
uint8_t* lpx_input() { return input; }
int16_t* lpx_output() { return output; }
uint32_t lpx_samples() { return sampleCount; }
uint32_t lpx_rate() { return sampleRate; }

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
