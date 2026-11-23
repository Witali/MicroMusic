#pragma once
#include <stdint.h>

// Host-only CUDA search ABI. These POD types deliberately need no CUDA headers.
// The caller must explicitly select CUDA; the portable C++ path remains separate.
static const int kLpxCudaMaxChoices = 512;
struct LpxCudaState { int h[10], ring[256], dd; };
struct LpxCudaChoice { int scale, lag, gain, step; };
struct LpxCudaJob {
    LpxCudaState initial;
    int16_t coefficients[8][10], samples[160];
    int cursor, profile, pre, count;
    LpxCudaChoice choices[kLpxCudaMaxChoices];
};
struct LpxCudaResult {
    LpxCudaState finalState;
    int pulses[8][2];
    double loss;
    int choice;
};

// One caller/device per process. Buffers and stream persist between calls.
// Failures are reported; these functions never silently execute the CPU path.
bool lpxCudaAvailable();
bool lpxCudaSearch(const LpxCudaJob& job, LpxCudaResult& result);
const char* lpxCudaError();
