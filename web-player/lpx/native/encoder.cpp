// Host-only C++ port of the project's speech_v4.py search, wav_lpc.py
// analysis, q0_model.py fixed arithmetic, and speech_v9.py wire packing.
// This is a bounded browser encoder, not firmware. No trained codebooks.
#include "Lpx4HybridCore.h"
#include "workspace.h"
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

namespace {
constexpr double pi = 3.14159265358979323846;
constexpr int pre = 13926;
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
struct State { int h[10], ring[256], dd; };
static State state;
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
void analyze(int frame) {
    double buf[256], r[11], a[11] = {1}, old[11], roots[10];
    double mean = 0;
    int start = frame * 160 + 80 - 128;
    for (int j = 0; j < 256; ++j) { int at = start + j; buf[j] = at >= 0 && at < padded ? emphasized[at] / 16384.0 : 0; mean += buf[j]; }
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
    for (int k = 0; k <= 10; ++k) { a[k] *= bandwidth; bandwidth *= .97; }
    int found = 0;
    for (int part = 0; part < 2; ++part) {
        double left = 1e-6, fl = rootValue(a, left, part);
        for (int grid = 1; grid <= 640; ++grid) {
            double right = pi * grid / 641, fr = rootValue(a, right, part);
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
                int norm = (vectors[fi ? fi - 1 : 0][j] * (16 - t) + vectors[fi][j] * t) >> 2;
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
double trial20(State& out, const State& initial, int cursor, int scale, int lag, int gain, int pos, int amp, bool save, double bound = HUGE_VAL) {
    out = initial; double loss = 0; const int16_t* co = coefficients[cursor / 20];
    for (int j = 0; j < 20; ++j) {
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
        for (int position = 0; position < (mode == 4 ? 16 : 20); ++position) {
            int pos = mode == 4 ? position + (position + 2) / 4 : position;
            for (int ai = 0; ai < (mode == 4 ? 2 : 16); ++ai) {
                int amp = mode == 4 ? (ai ? 8 : -8) : ai - 8;
                double error = trial20(trial, current, cursor, scale, lag, gain, pos, amp, false, best);
                if (error < best) { best = error; bestpos = pos; bestamp = amp; }
            }
        }
        loss += trial20(next, current, cursor, scale, lag, gain, bestpos, bestamp, save); current = next;
        if (save) { pulses[cursor / 20][0] = bestpos; pulses[cursor / 20][1] = bestamp; }
    }
    result = current; return loss;
}
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
int enc_begin(int samples, int profile, int sampleRate) {
    failure = 0; block = 0;
    if (samples < 1 || uint32_t(samples) > reservedSamples || (profile != 4 && profile != 6) || (sampleRate != 8000 && sampleRate != 12000 && sampleRate != 16000)) return -1;
    count = samples; padded = (count + 319) / 320 * 320; mode = profile; rate = sampleRate;
    headerBytes = count > 64000 ? 17 : 13;
    memset(source + count, 0, (padded - count) * sizeof(int16_t)); memset(&state, 0, sizeof(state));
    for (int j = 0; j < 256; ++j) window[j] = .54 - .46 * cos(2 * pi * j / 255);
    for (int j = 0; j < padded; ++j) emphasized[j] = source[j] / 2.0 - (j ? pre * (source[j - 1] / 2.0) / 16384 : 0);
    for (int fi = 0; fi < padded / 160; ++fi) analyze(fi);
    prepareCoefficients();
    for (int j = 0; j < padded; ++j) {
        residual[j] = emphasized[j];
        for (int k = 0; k < 10 && j > k; ++k) residual[j] += coefficients[j / 20][k] * emphasized[j - k - 1] / 4096;
    }
    return padded / 160;
}
int enc_step() {
    if (block >= padded / 160) return 100;
    int start = block * 160, lag = 18, pitchgain = 0; double power = 0, pitchscore = -1;
    for (int j = start; j < start + 160; ++j) power += residual[j] * residual[j];
    if (power == 0 && state.dd == 0) {
        bool silent = true; for (int k = 0; k < 10; ++k) if (state.h[k]) silent = false;
        if (silent) {
            State next; searchBlock(next, 0, 18, 0, true); state = next;
            params[block][0] = 0; params[block][1] = 18; params[block][2] = 0;
            ++block; return block * 100 / (padded / 160);
        }
    }
    double desired = fmax(1, sqrt(power / 160 * 20) / 8);
    int center = clip((int)nearbyint((128 + 16 * log2(desired / 16.384)) / 8), 1, 31);
    for (int candidate = 18; candidate <= 145; ++candidate) {
        double dot = 0, energy = 0;
        for (int j = start; j < start + 160; ++j) { double v = j >= candidate ? residual[j - candidate] : 0; dot += v * residual[j]; energy += v * v; }
        double positive = fmax(0, dot), score = positive * positive / (energy + 1);
        if (score > pitchscore) { pitchscore = score; lag = candidate; pitchgain = clip((int)nearbyint(8 * dot / (energy + 1)) * 2, 0, 14); }
    }
    double best = HUGE_VAL; int bestscale = 0, bestgain = 0; State trial;
    // Include zero and first nonzero step, as in allow_zero_scale=True.
    for (int scale = 0; scale <= 31; ++scale) {
        if (scale != 0 && scale != 6 && (scale < center - 2 || scale > center + 2)) continue;
        for (int choice = 0; choice < 3; ++choice) {
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
