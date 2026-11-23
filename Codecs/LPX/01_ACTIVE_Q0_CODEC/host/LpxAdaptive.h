#pragma once
#include <array>
#include <vector>
#include <stdint.h>

namespace lpx {
using Spectrum = std::array<int, 10>;
using Coefficients = std::array<int16_t, 10>;
using Parameters = std::array<int, 3>;
using Pulse = std::array<int, 2>;
using Pcm = std::vector<int16_t>;
struct SynthesisState { int h[10] = {}, ring[256] = {}, dd = 0, cc = 0; };
struct Stream {
    int samples = 0, rate = 8000, profile = 6, pre = 13926, bright = 0;
    int accuracy = 0; // Host-only policy; zero retains every legacy API.
    std::vector<Spectrum> spectra;
    std::vector<Parameters> parameters;
    std::vector<Pulse> pulses, extras;
    // Host-only continuation. Non-final windows must be multiples of1280,
    // preserving320/160/40/20-sample phases and the256-entry excitation ring.
    bool continuation=false, allowExtras=true;
    SynthesisState initial;
    Spectrum previousSpectrum={};
    std::array<int16_t,172> previousInput={};
    std::array<Coefficients,8> previousCoefficients={};
    Pcm lookahead;
};
int clamp(int value, int low = -32767, int high = 32767);
std::vector<Coefficients> coefficientTrace(const Stream& stream);
Pcm advance(const Stream& stream, const std::vector<Coefficients>& co, int start,
            int end, SynthesisState& state, std::vector<int>* lpc = nullptr);
Pcm render(const Stream& stream);
Stream canonicalAccuracy(const Stream& stream);
double emphasizedAt(const Stream& stream,const Pcm& reference,int at);
double residualBefore(const Stream& stream,const Pcm& reference,int at);
uint64_t sse(const Pcm& reference, const Pcm& actual, int start = 0);
Pcm pwm(const Pcm& pcm);
int spectralBits(const Stream& stream);
int compactBytes(const Stream& stream);
int extraCapacity(const Stream& stream, int maxBytes, int slots = -1);
std::vector<uint8_t> packV9(const Stream& stream);
Stream fitSeed(const Pcm& reference, int profile, int rate, int pre, bool zeroScale,
               double bandwidth = .97,const Stream* context = nullptr);
}
