// Shared host encoder: native PC and browser builds compile this same file.
// Search/analysis originate in speech_v4.py and wav_lpc.py; the integer
// model and V9 packing originate in q0_model.py and speech_v9.py.
#include "LpxEncoder.h"
#include "LpxSeed.h"
#include "Lpx4HybridCore.h"
#include "LpxHostWorkspace.h"
#include <stdint.h>
#include <string.h>
#include <math.h>

// Set to 0 to retain the exhaustive search as a correctness/performance oracle.
#ifndef LPX_ENCODER_ENABLE_PRUNING
#define LPX_ENCODER_ENABLE_PRUNING 1
#endif
#if LPX_ENCODER_ENABLE_PRUNING != 0 && LPX_ENCODER_ENABLE_PRUNING != 1
#error LPX_ENCODER_ENABLE_PRUNING must be 0 or 1
#endif
#ifndef LPX_ENCODER_DEDUP_CANDIDATES
#define LPX_ENCODER_DEDUP_CANDIDATES 1
#endif
#if LPX_ENCODER_DEDUP_CANDIDATES != 0 && LPX_ENCODER_DEDUP_CANDIDATES != 1
#error LPX_ENCODER_DEDUP_CANDIDATES must be 0 or 1
#endif
#ifndef LPX_ENCODER_REUSE_PREFIX
#define LPX_ENCODER_REUSE_PREFIX 1
#endif
#if LPX_ENCODER_REUSE_PREFIX != 0 && LPX_ENCODER_REUSE_PREFIX != 1
#error LPX_ENCODER_REUSE_PREFIX must be 0 or 1
#endif
#ifndef LPX_ENCODER_FAST_SILENCE
#define LPX_ENCODER_FAST_SILENCE 1
#endif
#if LPX_ENCODER_FAST_SILENCE != 0 && LPX_ENCODER_FAST_SILENCE != 1
#error LPX_ENCODER_FAST_SILENCE must be 0 or 1
#endif
#ifndef LPX_ENCODER_CACHE_ANALYSIS
#define LPX_ENCODER_CACHE_ANALYSIS 1
#endif
#if LPX_ENCODER_CACHE_ANALYSIS != 0 && LPX_ENCODER_CACHE_ANALYSIS != 1
#error LPX_ENCODER_CACHE_ANALYSIS must be 0 or 1
#endif
#ifndef LPX_ENCODER_SIMD_SEARCH
#define LPX_ENCODER_SIMD_SEARCH 0
#endif
#if LPX_ENCODER_SIMD_SEARCH != 0 && LPX_ENCODER_SIMD_SEARCH != 1
#error LPX_ENCODER_SIMD_SEARCH must be 0 or 1
#endif
#include "LpxEncoderSimd.h"
#ifndef LPX_ENCODER_ENABLE_CUDA
#define LPX_ENCODER_ENABLE_CUDA 0
#endif
#if LPX_ENCODER_ENABLE_CUDA != 0 && LPX_ENCODER_ENABLE_CUDA != 1
#error LPX_ENCODER_ENABLE_CUDA must be 0 or 1
#endif
#if LPX_ENCODER_ENABLE_CUDA
#include "LpxCuda.h"
#endif

namespace {
constexpr double pi = 3.14159265358979323846;
static int pre = 13926;
// Search-only LPC bandwidth expansion; all existing callers retain .97.
// The cached root basis depends only on frequency, not these coefficients.
static double analysisBandwidth = .97;
static bool allowZeroScale = true;
static bool referenceScaleOrder = false;
static const int16_t cosine[] = {
#include "cos_table.inc"
};
static const int16_t steps[] = {
#include "scale_table.inc"
};
static int16_t *source, *expected, (*coefficients)[10];
static double *emphasized, *residual, window[256];
static uint8_t (*spectra)[10], *packed;
static uint16_t (*vectors)[10];
static int (*params)[3], (*pulses)[2];
static uint32_t reservedSamples, packedCapacity;
static int headerBytes;
static int count, padded, mode, rate, block, bits, failure;
#if LPX_ENCODER_ENABLE_CUDA
using State = LpxCudaState;
static bool cudaEnabled;
#else
struct State { int h[10], ring[256], dd; };
#endif
static const char* backendError = "";
static State state;
static LpxSeedContext seedContext;
static bool hasSeedContext;
#if LPX_ENCODER_CACHE_ANALYSIS
static double rootGrid[2][641][11];
static bool analysisPrepared;
#endif
#if LPX_ENCODER_REUSE_PREFIX
// One cache per encoder instance, rebuilt for every subframe/scale/gain.
// Keep it off the 32 KiB stack. Full ring snapshots preserve lags 18 and 19.
static State prefixState[20];
static double prefixLoss[20];
#endif
int clip(int value, int low = -32767, int high = 32767) { return value < low ? low : value > high ? high : value; }
int polyMul(int value, int c) {
    if (value >= -250000 && value <= 250000) return (value * c) >> 12;
    int high = value / 16;
    return ((high * c) >> 8) + (((value - high * 16) * c) >> 12);
}
double rootValue(const double* a, double w, bool imaginary) {
    double result = 0;
    for (int k = 0; k <= 10; ++k) result += a[k] * (imaginary ? sin(w * (5.5 - k)) : cos(w * (5.5 - k)));
    return result;
}
void prepareAnalysis() {
#if LPX_ENCODER_CACHE_ANALYSIS
    if (analysisPrepared) return;
#endif
    for (int j = 0; j < 256; ++j) window[j] = .54 - .46 * cos(2 * pi * j / 255);
#if LPX_ENCODER_CACHE_ANALYSIS
    // Cache the original double expressions, without recurrence/interpolation.
    // The bisection between grid points still calls the original rootValue.
    for (int part = 0; part < 2; ++part) for (int grid = 0; grid <= 640; ++grid) {
        const double w = grid ? pi * grid / 641 : 1e-6;
        for (int k = 0; k <= 10; ++k) rootGrid[part][grid][k] = part ? sin(w * (5.5 - k)) : cos(w * (5.5 - k));
    }
    analysisPrepared = true;
#endif
}
#if LPX_ENCODER_CACHE_ANALYSIS
double gridRootValue(const double* a, int grid, int part) {
    double result = 0;
    for (int k = 0; k <= 10; ++k) result += a[k] * rootGrid[part][grid][k];
    return result;
}
#endif
void analyze(int frame) {
    double buf[256], r[11], a[11] = {1}, old[11], roots[10];
    double mean = 0;
    int start = frame * 160 + 80 - 128;
    for (int j = 0; j < 256; ++j) {
        int at=start+j;double sample=0;
        if(at>=0 && at<padded+(hasSeedContext?seedContext.lookahead:0))sample=emphasized[at];
        else if(at>=-48 && at<0 && hasSeedContext && seedContext.continuation)sample=seedContext.emphasized[at+48];
        buf[j]=sample/16384.0;mean+=buf[j];
    }
    mean /= 256;
    for (int j = 0; j < 256; ++j) buf[j] = (buf[j] - mean) * window[j];
    for (int lag = 0; lag <= 10; ++lag) { r[lag] = 0; for (int j = lag; j < 256; ++j) r[lag] += buf[j] * buf[j - lag]; }
    double error = fmax(r[0], 1e-10);
    for (int m = 1; m <= 10; ++m) {
        double sum = r[m]; for (int k = 1; k < m; ++k) sum += a[k] * r[m - k];
        double reflection = fmax(-.98, fmin(.98, -sum / fmax(error, 1e-12)));
        memcpy(old, a, sizeof(a));
        for (int k = 1; k < m; ++k) a[k] = old[k] + reflection * old[m - k];
        a[m] = reflection; error *= fmax(1e-4, 1 - reflection * reflection);
    }
    double bandwidth = 1;
    for (int k = 0; k <= 10; ++k) { a[k] *= bandwidth; bandwidth *= analysisBandwidth; }
    int found = 0;
    for (int part = 0; part < 2; ++part) {
        double left = 1e-6;
#if LPX_ENCODER_CACHE_ANALYSIS
        double fl = gridRootValue(a, 0, part);
#else
        double fl = rootValue(a, left, part);
#endif
        for (int grid = 1; grid <= 640; ++grid) {
            double right = pi * grid / 641;
#if LPX_ENCODER_CACHE_ANALYSIS
            double fr = gridRootValue(a, grid, part);
#else
            double fr = rootValue(a, right, part);
#endif
            if (fl * fr <= 0) {
                double lo = left, hi = right, flo = fl;
                for (int iteration = 0; iteration < 24; ++iteration) {
                    double mid = (lo + hi) * .5, value = rootValue(a, mid, part);
                    if (flo * value <= 0) hi = mid; else { lo = mid; flo = value; }
                }
                double w = (lo + hi) * .5;
                if (w > 1e-4 && w < pi - 1e-4) { if (found < 10) roots[found] = w / pi; ++found; }
            }
            left = right; fl = fr;
        }
    }
    if (found != 10) for (int j = 0; j < 10; ++j) roots[j] = (j + 1) / 11.0;
    else for (int j = 1; j < 10; ++j) { double value = roots[j]; int k = j; while (k && roots[k - 1] > value) { roots[k] = roots[k - 1]; --k; } roots[k] = value; }
    for (int j = 0; j < 10; ++j) vectors[frame][j] = clip((int)floor(roots[j] * 1023 + .5), 12, 1011);
    for (int j = 1; j < 10; ++j) if (vectors[frame][j] < vectors[frame][j - 1] + 12) vectors[frame][j] = vectors[frame][j - 1] + 12;
    if (vectors[frame][9] > 1011) { vectors[frame][9] = 1011; for (int j = 8; j >= 0; --j) if (vectors[frame][j] > vectors[frame][j + 1] - 12) vectors[frame][j] = vectors[frame][j + 1] - 12; }
}
void prepareCoefficients() {
    int frames = padded / 160, shift = mode == 4 ? 5 : 4, limit = mode == 4 ? 31 : 63;
    for (int fi = 0; fi < frames; fi += 2) {
        for (int j = 0; j < 10; ++j) spectra[fi / 2][j] = clip((int)nearbyint(((vectors[fi][j] + vectors[fi + 1][j]) * .5 - (1 << (shift - 1))) / (1 << shift)), 0, limit);
        for (int j = 1; j < 10; ++j) if (spectra[fi / 2][j] <= spectra[fi / 2][j - 1]) spectra[fi / 2][j] = spectra[fi / 2][j - 1] + 1;
        if (spectra[fi / 2][9] > limit) { spectra[fi / 2][9] = limit; for (int j = 8; j >= 0; --j) if (spectra[fi / 2][j] >= spectra[fi / 2][j + 1]) spectra[fi / 2][j] = spectra[fi / 2][j + 1] - 1; }
        for (int j = 0; j < 10; ++j) vectors[fi][j] = vectors[fi + 1][j] = (spectra[fi / 2][j] << shift) + (1 << (shift - 1));
    }
    for (int fi = 0; fi < frames; ++fi) {
        int endpoints[3][10];
        for (int point = 0; point < 3; ++point) {
            int t = point * 8, polynomials[2][12] = {{4096, 4096}, {4096, -4096}};
            for (int j = 0; j < 10; ++j) {
                int previous=fi?vectors[fi-1][j]:hasSeedContext && seedContext.continuation?seedContext.previousVector[j]:vectors[0][j];
                int norm = (previous * (16 - t) + vectors[fi][j] * t) >> 2;
                int index = norm >> 4, frac = norm & 15;
                int c = -(cosine[index] + ((cosine[index + 1] - cosine[index]) * frac >> 4));
                int* p = polynomials[j & 1]; int n = 2 + (j / 2) * 2;
                p[n + 1] = p[n - 1]; p[n] = p[n - 2] + polyMul(p[n - 1], c);
                for (int k = n - 1; k > 1; --k) p[k] = p[k - 2] + polyMul(p[k - 1], c) + p[k];
                p[1] = polyMul(p[0], c) + p[1];
            }
            for (int j = 0; j < 10; ++j) endpoints[point][j] = clip((polynomials[0][j + 1] + polynomials[1][j + 1]) / 2);
        }
        for (int sub = 0; sub < 8; ++sub) for (int j = 0; j < 10; ++j) {
            int a = endpoints[sub / 4][j], b = endpoints[sub / 4 + 1][j];
            coefficients[fi * 8 + sub][j] = clip(a + (b - a) * ((sub * 2 + 1) % 8) / 8);
        }
    }
}
double trial20(State& out, const State& initial, int cursor, int scale, int lag, int gain, int pos, int amp, bool save, double bound = HUGE_VAL, bool reusePrefix = false, bool recordPrefix = false) {
#if LPX_ENCODER_REUSE_PREFIX
    const int first = reusePrefix ? pos : 0;
    double loss = reusePrefix ? prefixLoss[pos] : 0;
#if LPX_ENCODER_ENABLE_PRUNING
    if (loss >= bound) return loss;
#endif
    out = reusePrefix ? prefixState[pos] : initial;
#else
    const int first = 0; double loss = 0; out = initial;
#endif
    const int16_t* co = coefficients[cursor / 20];
    for (int j = first; j < 20; ++j) {
#if LPX_ENCODER_REUSE_PREFIX
        if (recordPrefix) { prefixState[j] = out; prefixLoss[j] = loss; }
#endif
        int at = cursor + j, q = clip((gain * out.ring[(at - lag) & 255] + 8) >> 4, -32, 31);
        q = clip(q + (j == pos ? amp : 0), -32, 31); out.ring[at & 255] = q;
        int acc = 0; for (int k = 0; k < 10; ++k) acc += (co[k] * out.h[k]) >> 12;
        int pred = clip(q * steps[scale * 8] - acc);
        for (int k = 9; k; --k) out.h[k] = out.h[k - 1]; out.h[0] = pred;
        out.dd = clip(pred + ((pre * out.dd) >> 14));
        int sample = clip(clip(out.dd, -16384, 16384) * 2, -32768, 32767);
        double delta = sample - source[at]; loss += delta * delta;
        if (save) expected[at] = sample;
#if LPX_ENCODER_ENABLE_PRUNING
        // Squared errors cannot decrease. Ties keep the earlier candidate;
        // this partial state is discarded. Winner replay has an infinite bound.
        if (loss >= bound) return loss;
#endif
    }
    return loss;
}
double searchBlock(State& result, int scale, int lag, int gain, bool save, double bound = HUGE_VAL) {
    State current = state, trial, next; double loss = 0;
    for (int si = 0; si < 8; ++si) {
#if LPX_ENCODER_ENABLE_PRUNING
        if (loss >= bound) { result = current; return loss; }
#endif
        int cursor = block * 160 + si * 20, bestpos = 0, bestamp = 0; double best = HUGE_VAL;
#if LPX_ENCODER_REUSE_PREFIX
        // No impulse before a candidate's position: compute that prefix once.
        trial20(trial, current, cursor, scale, lag, gain, 20, 0, false, HUGE_VAL, false, true);
#endif
        for (int position = 0; position < (mode == 4 ? 16 : 20); ++position) {
            int pos = mode == 4 ? position + (position + 2) / 4 : position;
#if LPX_ENCODER_HAS_SIMD_SEARCH
            for (int ai = 0; ai < (mode == 4 ? 2 : 16); ai += mode == 4 ? 2 : 4) {
                const int n = mode == 4 ? 2 : 4;
                int amplitudes[4]; double errors[4];
                for (int lane = 0; lane < 4; ++lane) amplitudes[lane] = mode == 4 ? (lane & 1 ? 8 : -8) : ai + lane - 8;
                const State& prefix = prefixState[pos];
                lpxTrial4(errors, prefix.h, prefix.ring, prefix.dd, coefficients[cursor / 20], source + cursor,
                    cursor, steps[scale * 8], lag, gain, pos, amplitudes, prefixLoss[pos], best, LPX_ENCODER_ENABLE_PRUNING, pre);
                // Preserve the original strict first-winner order within a batch.
                for (int lane = 0; lane < n; ++lane) if (errors[lane] < best) {
                    best = errors[lane]; bestpos = pos; bestamp = amplitudes[lane];
                }
            }
#else
            for (int ai = 0; ai < (mode == 4 ? 2 : 16); ++ai) {
                int amp = mode == 4 ? (ai ? 8 : -8) : ai - 8;
                double error = trial20(trial, current, cursor, scale, lag, gain, pos, amp, false, best, true);
                if (error < best) { best = error; bestpos = pos; bestamp = amp; }
            }
#endif
        }
        loss += trial20(next, current, cursor, scale, lag, gain, bestpos, bestamp, save); current = next;
        if (save) { pulses[cursor / 20][0] = bestpos; pulses[cursor / 20][1] = bestamp; }
    }
    result = current; return loss;
}
#if LPX_ENCODER_FAST_SILENCE
void commitSilentBlock(int start) {
    // Under the existing zero-residual/zero-filter guard, scale=0/gain=0
    // synthesizes zero for every candidate. Strict ties choose pos=0, amp=-8.
    // Preserve those excitation pulses, including the untouched ring entries.
    for (int j = 0; j < 160; ++j) {
        state.ring[(start + j) & 255] = j % 20 == 0 ? -8 : 0;
        expected[start + j] = 0;
    }
    for (int si = 0; si < 8; ++si) {
        pulses[start / 20 + si][0] = 0;
        pulses[start / 20 + si][1] = -8;
    }
}
#endif
void put(int value, int width) {
    for (int bit = 0; bit < width; ++bit) {
        if (headerBytes + (bits >> 3) >= packedCapacity) { failure = 1; return; }
        packed[headerBytes + (bits >> 3)] |= ((value >> bit) & 1) << (bits & 7); ++bits;
    }
}
int riceCost(int value, int k, int width) { return value >> k >= 8 ? 8 + width : (value >> k) + 1 + k; }
void rice(int value, int k, int width) {
    int q = value >> k;
    if (q >= 8) { put(0, 8); put(value, width); }
    else { put(0, q); put(1, 1); put(value & ((1 << k) - 1), k); }
}
void word(int offset, int value) { packed[offset] = value; packed[offset + 1] = value >> 8; }
void dword(int offset, uint32_t value) { word(offset, value & 65535); word(offset + 2, value >> 16); }
}

extern "C" {
int enc_set_backend(int backend) {
    backendError = "";
    if (backend != 0 && backend != 1) { backendError = "Unknown encoding backend"; return -1; }
#if LPX_ENCODER_ENABLE_CUDA
    if (backend && !lpxCudaAvailable()) { backendError = lpxCudaError(); return -1; }
    cudaEnabled = backend != 0;
    return 0;
#else
    if (backend) { backendError = "CUDA backend was not enabled in this build"; return -1; }
    return 0;
#endif
}
const char* enc_backend_error() { return backendError; }
int enc_reserve(uint32_t samples) {
    reservedSamples = 0;
    if (!samples || samples > kLpxMaxSamples) return 0;
    const uint32_t n = (samples + 319) / 320 * 320;
    uint8_t* memory = static_cast<uint8_t*>(reserveWorkspace(n * 24 + 65536));
    if (!memory) return 0;
    uintptr_t at = reinterpret_cast<uintptr_t>(memory);
    auto take = [&at](uint32_t bytes) -> void* { uintptr_t result = at; at += (bytes + 7) & ~uintptr_t(7); return reinterpret_cast<void*>(result); };
    source = static_cast<int16_t*>(take(n * 2)); expected = static_cast<int16_t*>(take(n * 2));
    coefficients = static_cast<int16_t(*)[10]>(take(n));
    emphasized = static_cast<double*>(take(n * 8)); residual = static_cast<double*>(take(n * 8));
    spectra = static_cast<uint8_t(*)[10]>(take(n / 320 * 10));
    vectors = static_cast<uint16_t(*)[10]>(take(n / 160 * 20));
    params = static_cast<int(*)[3]>(take(n / 160 * 12)); pulses = static_cast<int(*)[2]>(take(n / 20 * 8));
    packedCapacity = 17 + n / 320 * 64; packed = static_cast<uint8_t*>(take(packedCapacity));
    reservedSamples = samples;
    return 1;
}
int16_t* enc_input() { return source; }
uint8_t* enc_output() { return packed; }
}
int lpxSeedBegin(int samples, int profile, int sampleRate, int emphasis, bool zeroScale,
                 double bandwidth) {
    return lpxSeedBeginContext(samples,profile,sampleRate,emphasis,zeroScale,bandwidth,nullptr);
}
int lpxSeedBeginContext(int samples,int profile,int sampleRate,int emphasis,bool zeroScale,double bandwidth,const LpxSeedContext* context) {
    pre = emphasis; allowZeroScale = zeroScale; referenceScaleOrder = true;
    hasSeedContext=context!=nullptr;if(context)seedContext=*context;
    failure = 0; block = 0;
    if (samples < 1 || uint32_t(samples) > reservedSamples || (profile != 4 && profile != 6) || (sampleRate != 8000 && sampleRate != 12000 && sampleRate != 16000)) return -1;
    if (!(bandwidth > 0 && bandwidth <= 1)) return -1;
    analysisBandwidth = bandwidth;
    count = samples; padded = (count + 319) / 320 * 320; mode = profile; rate = sampleRate;
    headerBytes = count > 64000 ? 17 : 13;
    memset(source + count, 0, (padded - count) * sizeof(int16_t)); memset(&state, 0, sizeof(state));
    if(hasSeedContext) { memcpy(state.h,seedContext.h,sizeof(state.h));memcpy(state.ring,seedContext.ring,sizeof(state.ring));state.dd=seedContext.dd; }
    prepareAnalysis();
    for (int j = 0; j < padded+(hasSeedContext?seedContext.lookahead:0); ++j)
        emphasized[j] = source[j] / 2.0 - (j ? pre * (source[j - 1] / 2.0) / 16384 : hasSeedContext && seedContext.continuation?pre*(seedContext.lastSample/2.0)/16384:0);
    for (int fi = 0; fi < padded / 160; ++fi) analyze(fi);
    prepareCoefficients();
    for (int j = 0; j < padded; ++j) {
        residual[j] = emphasized[j];
        for (int k = 0; k < 10; ++k) {
            int at=j-k-1;
            if(at>=0)residual[j] += coefficients[j / 20][k] * emphasized[at] / 4096;
            else if(hasSeedContext && seedContext.continuation)residual[j] += coefficients[j / 20][k] * seedContext.emphasized[at+48] / 4096;
        }
    }
    return padded / 160;
}
LpxSeedView lpxSeedView() { return {spectra, params, pulses, expected, failure == 0 && block == padded / 160}; }
uint32_t lpxSeedCapacity() { return reservedSamples; }
extern "C" {
int enc_begin(int samples, int profile, int sampleRate) {
    int result = lpxSeedBegin(samples, profile, sampleRate, 13926, true);
    referenceScaleOrder = false;
    return result;
}
int enc_step() {
    if (failure) return failure < 0 ? failure : -2;
    if (block >= padded / 160) return 100;
    int start = block * 160, lag = 18, pitchgain = 0; double power = 0, pitchscore = -1;
    for (int j = start; j < start + 160; ++j) power += residual[j] * residual[j];
    if (allowZeroScale && power == 0 && state.dd == 0) {
        bool silent = true; for (int k = 0; k < 10; ++k) if (state.h[k]) silent = false;
        if (silent) {
#if LPX_ENCODER_FAST_SILENCE
            commitSilentBlock(start);
#else
            State next; searchBlock(next, 0, 18, 0, true); state = next;
#endif
            params[block][0] = 0; params[block][1] = 18; params[block][2] = 0;
            ++block; return block * 100 / (padded / 160);
        }
    }
    double desired = fmax(1, sqrt(power / 160 * 20) / 8);
    int center = clip((int)nearbyint((128 + 16 * log2(desired / 16.384)) / 8), 1, 31);
    for (int candidate = 18; candidate <= 145; ++candidate) {
        double dot = 0, energy = 0;
        for (int j = start; j < start + 160; ++j) { double v = j >= candidate ? residual[j - candidate] : hasSeedContext && seedContext.continuation?seedContext.residual[j-candidate+145]:0; dot += v * residual[j]; energy += v * v; }
        double positive = fmax(0, dot), score = positive * positive / (energy + 1);
        if (score > pitchscore) { pitchscore = score; lag = candidate; pitchgain = clip((int)nearbyint(8 * dot / (energy + 1)) * 2, 0, 14); }
    }
    double best = HUGE_VAL; int bestscale = 0, bestgain = 0; State trial;
    int codes[7], codeCount = 0;
    if (referenceScaleOrder) {
        // Python tests its original neighborhood first, then appends zero/unit
        // step. This tie order is part of adaptive seed equivalence.
        for (int scale = clip(center-2,0,31); scale <= clip(center+2,0,31); ++scale) codes[codeCount++] = scale;
        if (allowZeroScale) for (int extra=0;extra<2;++extra) {
            int scale=extra?6:0;
            bool seen = false;for (int i=0;i<codeCount;++i) seen |= codes[i]==scale;
            if (!seen) codes[codeCount++] = scale;
        }
    } else for (int scale=0;scale<=31;++scale)
        if ((allowZeroScale && (scale==0 || scale==6)) || (scale>=center-2 && scale<=center+2)) codes[codeCount++]=scale;
#if LPX_ENCODER_ENABLE_CUDA
    if (cudaEnabled) {
        static LpxCudaJob job;
        job.initial = state; job.cursor = start; job.profile = mode; job.pre = pre; job.count = 0;
        memcpy(job.samples, source + start, sizeof(job.samples));
        memcpy(job.coefficients, coefficients + start / 20, sizeof(job.coefficients));
        for (int ci = 0; ci < codeCount; ++ci) {
            int scale = codes[ci]; bool duplicate = false;
#if LPX_ENCODER_DEDUP_CANDIDATES
            for (int p = 0; p < ci; ++p) duplicate |= steps[codes[p] * 8] == steps[scale * 8];
#endif
            if (duplicate) continue;
            for (int choice = 0; choice < 3; ++choice) {
#if LPX_ENCODER_DEDUP_CANDIDATES
                if (choice == 2 && pitchgain == 14) continue;
#endif
                int gain = choice == 0 ? 0 : choice == 1 ? pitchgain : 14;
                if (choice && !gain) continue;
                job.choices[job.count++] = {scale, lag, gain, steps[scale * 8]};
            }
        }
        LpxCudaResult result;
        if (!lpxCudaSearch(job, result)) { backendError = lpxCudaError(); failure = -7; return failure; }
        if (result.choice < 0 || result.choice >= job.count) { backendError = "Invalid CUDA winner"; failure = -7; return failure; }
        const auto& selected = job.choices[result.choice];
        // Reconstruct the GPU winner through portable C arithmetic. This is a
        // full state/PCM check, independent of GPU arithmetic and reductions.
        State current = state, next; double loss = 0;
        for (int si = 0; si < 8; ++si) {
            int position = result.pulses[si][0], amplitude = result.pulses[si][1];
            if (position < 0 || position >= 20 || (mode == 4 ? (position % 5 == 2 || (amplitude != -8 && amplitude != 8)) : (amplitude < -8 || amplitude > 7))) {
                backendError = "Invalid CUDA pulse"; failure = -7; return failure;
            }
            loss += trial20(next,current,start+si*20,selected.scale,selected.lag,selected.gain,position,amplitude,true);
            current = next;
            pulses[start / 20 + si][0] = position; pulses[start / 20 + si][1] = amplitude;
        }
        if (loss != result.loss || memcmp(&current,&result.finalState,sizeof(current))) {
            backendError = "CUDA winner differs from portable synthesis"; failure = -7; return failure;
        }
        state = current;
        params[block][0] = selected.scale; params[block][1] = selected.lag; params[block][2] = selected.gain;
        ++block; return block * 100 / (padded / 160);
    }
#endif
    for (int codeIndex=0;codeIndex<codeCount;++codeIndex) {
        int scale=codes[codeIndex];
#if LPX_ENCODER_DEDUP_CANDIDATES
        // Several wire codes have the same integer step. Retain the first
        // admitted code, including its tie priority and stored ring history.
        bool duplicate = false;
        for (int previous = 0; previous < codeIndex; ++previous) {
            if (steps[codes[previous] * 8] == steps[scale * 8]) duplicate = true;
        }
        if (duplicate) continue;
#endif
        for (int choice = 0; choice < 3; ++choice) {
#if LPX_ENCODER_DEDUP_CANDIDATES
            if (choice == 2 && pitchgain == 14) continue;
#endif
            int gain = choice == 0 ? 0 : choice == 1 ? pitchgain : 14;
            if (choice && !gain) continue;
            double error = searchBlock(trial, scale, lag, gain, false, best);
            if (error < best) { best = error; bestscale = scale; bestgain = gain; }
        }
    }
    searchBlock(trial, bestscale, lag, bestgain, true); state = trial;
    params[block][0] = bestscale; params[block][1] = lag; params[block][2] = bestgain;
    ++block; return block * 100 / (padded / 160);
}
int enc_finish() {
    if (failure) return failure < 0 ? failure : -2;
    if (block != padded / 160) return -1;
    memset(packed, 0, packedCapacity); bits = 0;
    int spectralBits = mode == 4 ? 5 : 6;
    for (int frame = 0; frame < padded / 320; ++frame) {
        bool repeat = frame && memcmp(spectra[frame], spectra[frame - 1], 10) == 0;
        put(!repeat, 1);
        if (!repeat) {
            int gap[10], delta[10], gapCost = 0, deltaCost = frame ? 0 : 100000;
            for (int j = 0; j < 10; ++j) {
                gap[j] = spectra[frame][j] - (j ? spectra[frame][j - 1] + 1 : 0);
                gapCost += riceCost(gap[j], spectralBits == 5 ? 1 : 2, spectralBits);
                int difference = frame ? spectra[frame][j] - spectra[frame - 1][j] : 0;
                delta[j] = difference >= 0 ? 2 * difference : -2 * difference - 1;
                deltaCost += riceCost(delta[j], spectralBits == 5 ? 0 : 1, spectralBits + 1);
            }
            bool useDelta = deltaCost < gapCost; put(useDelta, 1);
            for (int j = 0; j < 10; ++j) rice(useDelta ? delta[j] : gap[j], (spectralBits == 5 ? 1 : 2) - (useDelta ? 1 : 0), spectralBits + (useDelta ? 1 : 0));
        }
        for (int half = 0; half < 2; ++half) {
            int base = frame * 320 + half * 160;
            if (base >= count) break;
            int* param = params[frame * 2 + half]; put(param[0], 5); put(param[2] / 2, 3);
            if (param[2]) put(param[1] - 18, 7);
            for (int packet = 0; packet < 4 && base + packet * 40 < count; ++packet) {
                int* a = pulses[base / 20 + packet * 2]; int* b = pulses[base / 20 + packet * 2 + 1];
                if (mode == 4) { put(a[0] - (a[0] + 2) / 5, 4); put(a[1] > 0, 1); put(b[0] - (b[0] + 2) / 5, 4); put(b[1] > 0, 1); }
                else { put((a[0] & 3) | ((b[0] & 3) << 2), 4); put((a[0] >> 2) + 5 * (b[0] >> 2), 5); put(a[1] & 15, 4); put(b[1] & 15, 4); }
            }
        }
    }
    int size = headerBytes + (bits + 7) / 8;
    if (failure) return -2;
    packed[0] = 'L'; packed[1] = '9'; packed[2] = mode | (headerBytes == 17 ? 64 : 0);
    word(3, rate);
    if (headerBytes == 17) { dword(5, count); word(9, pre); word(11, 0); dword(13, size - 17); }
    else { word(5, count); word(7, pre); word(9, 0); word(11, size - 13); }
    // Validate the entire continuous stream against the shared C decoder.
    Lpx4HybridCore decoder;
    if (!decoder.beginWideV9(packed, size)) return -3;
    for (int j = 0; j < count; ++j) { int16_t sample; if (!decoder.nextS16(sample) || sample != expected[j]) return -4; }
    int16_t tail;
    if (decoder.nextS16(tail) || decoder.error() || !decoder.finished()) return -5;
    return size;
}
}
