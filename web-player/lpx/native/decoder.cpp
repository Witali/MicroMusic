// Browser ABI for the unmodified, portable LPX V9 C arithmetic backend.
#include "Lpx4HybridCore.h"
#include <stdint.h>

static uint8_t input[65535];
static int16_t output[64000];
static uint32_t sampleCount, sampleRate;

extern "C" {
uint8_t* lpx_input() { return input; }
int16_t* lpx_output() { return output; }
uint32_t lpx_samples() { return sampleCount; }
uint32_t lpx_rate() { return sampleRate; }

// 0: success, -1: size/header, -2: payload (including strict final EOF).
int lpx_decode(uint32_t bytes) {
    sampleCount = sampleRate = 0;
    if (bytes < 13 || bytes > sizeof(input)) return -1;
    Lpx4HybridCore core;
    if (!core.begin(input, static_cast<uint16_t>(bytes))) return -1;
    const uint32_t count = core.samples();
    if (!count || count > 64000) return -1;
    uint32_t position = 0;
    while (position < count && core.nextS16(output[position])) ++position;
    int16_t tail;
    if (position != count || core.nextS16(tail) || core.error() || !core.finished()) return -2;
    sampleCount = count;
    sampleRate = core.sampleRate();
    return 0;
}
}
