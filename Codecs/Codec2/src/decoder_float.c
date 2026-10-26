/* LGPL-2.1. Derived from David Rowe's Codec2 1.2.0 codec2.c, quantise.c,
 * phase.c, postfilter.c and sine.c. Original sources/notices are in vendor/.
 * Memory changes: one model, one shared FFT configuration, in-place real FFT
 * buffers, and scalar phase temporaries. No harmonics or algorithm stages cut.
 */
#include "codec2_decoder.h"
#include "codec2_3200.h"
#include <math.h>
#include <float.h>
#include <string.h>
#include "defines.h"
#include "kiss_fftr.h"
#include "_kiss_fft_guts.h"
#include "lsp.h"

#if defined(USE_SIMD) || defined(FIXED_POINT)
#error This profile requires original scalar float KISS FFT
#endif
#if FLT_RADIX != 2 || FLT_MANT_DIG != 24
#error This baseline requires IEEE binary32 float
#endif
typedef char codec2_binary32_size[(sizeof(float) == 4) ? 1 : -1];

/* Same tag/members as the pinned kiss_fftr.c. Only the direction and twiddle
 * signs change; tmpbuf stays scratch. The original allocation API sizes it.
 */
struct kiss_fftr_state {
    kiss_fft_cfg substate;
    kiss_fft_cpx *tmpbuf;
    kiss_fft_cpx *super_twiddles;
};

typedef struct {
    float wo;
    int harmonics;
    int voiced;
    float amplitude[81];
    float phase[81];
} harmonic_model;

typedef union {
    float time[514];
    kiss_fft_cpx frequency[257];
} real_transform;

#ifdef CODEC2_DECODER_TRACE
float codec2_decoder_trace[2][64];
#endif

static void direction(kiss_fftr_cfg cfg, int inverse) {
    if (cfg->substate->inverse == inverse) return;
    cfg->substate->inverse = inverse;
    for (int i = 0; i < cfg->substate->nfft; ++i)
        cfg->substate->twiddles[i].i = -cfg->substate->twiddles[i].i;
    for (int i = 0; i < cfg->substate->nfft / 2; ++i)
        cfg->super_twiddles[i].i = -cfg->super_twiddles[i].i;
}

static unsigned random_value(codec2_decoder *state) {
    state->random_state = state->random_state * UINT32_C(1103515245) + UINT32_C(12345);
    return (unsigned)((state->random_state >> 16) & 32767);
}

static int harmonic_count(float wo) {
    /* AVR-GCC has 32-bit double, while the original native PI literal is
     * binary64. At minimum Wo, native truncation gives 79, AVR division 80.
     * One extra UV harmonic changes every later RNG draw. Compare the exact
     * binary32 mantissa product to the canonical PI threshold instead.
     * Wo's exponent is -5..-2 for every legal 3200 pitch/interpolation.
     */
    uint32_t bits;
    memcpy(&bits, &wo, sizeof(bits));
    int exponent = (int)((bits >> 23) & 255) - 127;
    uint32_t mantissa = (bits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    uint32_t threshold = UINT32_C(3373259426) >> (7 + exponent); /* floor(PI*2^(23-exponent)) */
    int count = (int)(PI / wo);
    while ((uint32_t)count * mantissa > threshold) --count;
    while ((uint32_t)(count + 1) * mantissa <= threshold) ++count;
    return count;
}

static int band_boundary(int twice_harmonic, float wo, float radians_per_bin) {
    uint32_t wbits, rbits;
    memcpy(&wbits, &wo, sizeof(wbits));
    memcpy(&rbits, &radians_per_bin, sizeof(rbits));
    uint32_t wm = (wbits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    uint32_t rm = (rbits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    int shift = (int)((wbits >> 23) & 255) - (int)((rbits >> 23) & 255);
    uint64_t numerator = ((uint64_t)twice_harmonic * wm << shift) + rm;
    uint32_t denominator = 2 * rm;
    int count = (int)((0.5 * twice_harmonic) * wo / radians_per_bin + 0.5);
    /* Native uses binary64 for (m +/- .5)*Wo/r; AVR rounds it in binary32.
     * Exact dyadic-ratio comparisons stabilize half-bin control decisions.
     */
    while ((uint64_t)count * denominator > numerator) --count;
    while ((uint64_t)(count + 1) * denominator <= numerator) ++count;
    return count;
}

static int synthesis_bin(float harmonic_angle) {
    float scaled = harmonic_angle * 512;
    uint32_t bits;
    memcpy(&bits, &scaled, sizeof(bits));
    int exponent = (int)((bits >> 23) & 255) - 127;
    uint32_t mantissa = (bits & UINT32_C(0x7fffff)) | UINT32_C(0x800000);
    uint64_t exact = (uint64_t)mantissa << (exponent + 25); /* scaled * 2^48 */
    const uint64_t half_two_pi = UINT64_C(884279718978280); /* floor((6.283185307/2)*2^48) */
    int count = (int)(scaled / TWO_PI + 0.5);
    while (count > 0 && exact < (uint64_t)(2 * count - 1) * half_two_pi) --count;
    while (exact >= (uint64_t)(2 * count + 1) * half_two_pi) ++count;
    return count;
}

int codec2_decoder_init(codec2_decoder *state) {
    if (!state) return -1;
    size_t needed = 0;
    kiss_fftr_alloc(512, 0, NULL, &needed);
    if (needed > sizeof(state->fft_storage.bytes)) return -1;
    memset(state, 0, sizeof(*state));
    size_t capacity = sizeof(state->fft_storage.bytes);
    state->fft_config = kiss_fftr_alloc(512, 0, state->fft_storage.bytes, &capacity);
    if (!state->fft_config) return -1;
    state->fft_bytes = (uint16_t)capacity;
    state->previous_wo = TWO_PI / 160;
    state->previous_energy = 1;
    state->random_state = 1;
    for (int i = 0; i < 10; ++i) state->previous_lsp[i] = i * PI / 11;
    float win = 0;
    for (int i = 0; i < 80; ++i, win += 1.0 / 80) state->synthesis_window[i] = win;
    win = 1;
    for (int i = 80; i < 160; ++i, win -= 1.0 / 80) state->synthesis_window[i] = win;
    state->initialized = 1;
    return 0;
}

static void spectral_amplitudes(kiss_fftr_cfg cfg, float ak[11], harmonic_model *model,
                                float energy, real_transform *analysis) {
    float power[256];
    real_transform weighting;
    memset(analysis->time, 0, 512 * sizeof(float));
    for (int i = 0; i <= 10; ++i) analysis->time[i] = ak[i];
    /* The pinned real KISS path reads all input into cfg->tmpbuf before
     * writing any output, in both directions. The union makes overlap explicit.
     */
    kiss_fftr(cfg, analysis->time, analysis->frequency);
    for (int i = 0; i < 256; ++i) {
        float real = analysis->frequency[i].r, imag = analysis->frequency[i].i;
        power[i] = 1.0 / (real * real + imag * imag + 1E-6);
    }
    memset(weighting.time, 0, 512 * sizeof(float));
    weighting.time[0] = ak[0];
    float coefficient = 0.5;
    for (int i = 1; i <= 10; ++i) {
        weighting.time[i] = ak[i] * coefficient;
        coefficient *= 0.5;
    }
    kiss_fftr(cfg, weighting.time, weighting.frequency);
    for (int i = 0; i < 256; ++i)
        weighting.frequency[i].r = weighting.frequency[i].r * weighting.frequency[i].r
                                + weighting.frequency[i].i * weighting.frequency[i].i;
    for (int i = 0; i < 256; ++i)
        weighting.frequency[i].r = sqrtf(weighting.frequency[i].r * power[i]);
    float before = 1E-4, after = 1E-4;
    for (int i = 0; i < 256; ++i) before += power[i];
    for (int i = 0; i < 256; ++i) {
        float factor = powf(weighting.frequency[i].r, 0.2f);
        power[i] *= factor * factor;
        after += power[i];
    }
    float gain = before / after;
    gain *= energy;
    for (int i = 0; i < 256; ++i) power[i] *= gain;
    for (int i = 0; i < 64; ++i) power[i] *= 1.4 * 1.4;
    float r = TWO_PI / 512;
    for (int m = 1; m <= model->harmonics; ++m) {
        int first = band_boundary(2 * m - 1, model->wo, r);
        int last = band_boundary(2 * m + 1, model->wo, r);
        if (last > 256) last = 256;
        float sum = 0;
        for (int i = first; i < last; ++i) sum += power[i];
        model->amplitude[m] = sqrtf(sum);
    }
    if (model->wo < (PI * 150.0 / 4000)) model->amplitude[1] *= 0.032;
}

static void phases(codec2_decoder *state, harmonic_model *model, const real_transform *analysis) {
    state->excitation_phase += model->wo * 80;
    state->excitation_phase -= TWO_PI * floorf(state->excitation_phase / TWO_PI + 0.5);
    float r = TWO_PI / 512;
    for (int m = 1; m <= model->harmonics; ++m) {
        int bin = (int)(m * model->wo / r + 0.5);
        float angle = model->voiced ? state->excitation_phase * m
                                   : (float)(TWO_PI * (float)random_value(state) / 32767);
        float real = cosf(angle), imag = sinf(angle);
        float hr = analysis->frequency[bin].r, hi = -analysis->frequency[bin].i;
        float ar = hr * real - hi * imag;
        float ai = hi * real + hr * imag;
        model->phase[m] = atan2f(ai, ar + 1E-12);
    }
    float energy = 1E-12;
    for (int m = 1; m <= model->harmonics; ++m)
        energy += model->amplitude[m] * model->amplitude[m];
    energy = 10.0 * log10f(energy / model->harmonics);
    if (energy < 40.0 && !model->voiced)
        state->background = state->background * (1.0 - 0.1) + energy * 0.1;
    float threshold = POW10F((state->background + 6.0) / 20.0);
    if (model->voiced)
        for (int m = 1; m <= model->harmonics; ++m)
            if (model->amplitude[m] < threshold)
                model->phase[m] = (TWO_PI / 32767) * (float)random_value(state);
}

static void synthesise(codec2_decoder *state, harmonic_model *model, int16_t *pcm) {
    real_transform synthesis;
    for (int i = 0; i < 79; ++i) state->overlap[i] = state->overlap[i + 80];
    state->overlap[79] = 0;
    memset(synthesis.frequency, 0, sizeof(synthesis.frequency));
    for (int m = 1; m <= model->harmonics; ++m) {
        int bin = synthesis_bin(m * model->wo);
        if (bin > 255) bin = 255;
        synthesis.frequency[bin].r = model->amplitude[m] * cosf(model->phase[m]);
        synthesis.frequency[bin].i = model->amplitude[m] * sinf(model->phase[m]);
    }
    kiss_fftr_cfg cfg = (kiss_fftr_cfg)state->fft_config;
    direction(cfg, 1);
    kiss_fftri(cfg, synthesis.frequency, synthesis.time);
    for (int i = 0; i < 79; ++i)
        state->overlap[i] += synthesis.time[512 - 80 + 1 + i] * state->synthesis_window[i];
    for (int i = 79, j = 0; i < 160; ++i, ++j)
        state->overlap[i] = synthesis.time[j] * state->synthesis_window[i];
    float maximum = 0;
    for (int i = 0; i < 80; ++i)
        if (state->overlap[i] > maximum) maximum = state->overlap[i];
    float over = maximum / 30000.0;
    if (over > 1.0) {
        float gain = 1.0 / (over * over);
        for (int i = 0; i < 80; ++i) state->overlap[i] *= gain;
    }
    for (int i = 0; i < 80; ++i) {
        float sample = state->overlap[i];
        pcm[i] = sample > 32767.0 ? 32767 : sample < -32767.0 ? -32767 : (int16_t)sample;
    }
}

int codec2_decoder_decode(codec2_decoder *state, const uint8_t *packet, size_t length, int16_t *pcm) {
    if (!state || !state->initialized || !packet || !pcm || length != 8) return -1;
    codec2_3200_params params;
    codec2_3200_unpack(packet, length, &params);
    float current_lsp[10], lsp[10], ak[11];
    float wo_min = TWO_PI / 160, wo_max = TWO_PI / 20;
    float step = (wo_max - wo_min) / 128;
    float next_wo = wo_min + step * params.pitch_index;
    float energy_db = -10.0 + (50.0f / 32) * params.energy_index;
    float next_energy = POW10F(energy_db / 10.0);
    for (int i = 0; i < 10; ++i) current_lsp[i] = (PI / 4000.0) * (25.0f * params.lsp_25hz[i]);
    for (int half = 0; half < 2; ++half) {
        harmonic_model model;
        real_transform analysis;
        model.voiced = params.voiced[half];
        model.wo = next_wo;
        float energy = next_energy;
        if (!half) {
            if (model.voiced && !state->previous_voiced && !params.voiced[1]) model.voiced = 0;
            if (model.voiced) {
                if (state->previous_voiced && params.voiced[1]) model.wo = (1.0 - 0.5) * state->previous_wo + 0.5f * next_wo;
                if (state->previous_voiced && !params.voiced[1]) model.wo = state->previous_wo;
            } else model.wo = wo_min;
            energy = sqrtf(state->previous_energy * next_energy);
            for (int i = 0; i < 10; ++i) lsp[i] = (1.0 - 0.5) * state->previous_lsp[i] + 0.5f * current_lsp[i];
        } else memcpy(lsp, current_lsp, sizeof(lsp));
        model.harmonics = harmonic_count(model.wo);
        /* Mode 3200 at 8 kHz has a 50-Hz minimum, hence at most 80 harmonics. */
        if (model.harmonics < 1 || model.harmonics > 80) return -2;
        lsp_to_lpc(lsp, ak, 10);
        kiss_fftr_cfg cfg = (kiss_fftr_cfg)state->fft_config;
        direction(cfg, 0);
        spectral_amplitudes(cfg, ak, &model, energy, &analysis);
#ifdef CODEC2_DECODER_TRACE
        float *trace = codec2_decoder_trace[half];
        trace[0] = model.wo; trace[1] = energy; trace[2] = model.voiced; trace[3] = model.harmonics;
        for (int j = 0; j < 10; ++j) trace[4 + j] = lsp[j];
        for (int j = 0; j < 11; ++j) trace[14 + j] = ak[j];
        for (int j = 0; j < 8; ++j) {
            trace[25 + j] = model.amplitude[j + 1];
            int bin = (int)((j + 1) * model.wo / (float)(TWO_PI / 512) + 0.5);
            trace[41 + 2 * j] = analysis.frequency[bin].r;
            trace[42 + 2 * j] = analysis.frequency[bin].i;
        }
#endif
        phases(state, &model, &analysis);
#ifdef CODEC2_DECODER_TRACE
        for (int j = 0; j < 8; ++j) trace[33 + j] = model.phase[j + 1];
        trace[57] = state->excitation_phase; trace[58] = state->background;
        trace[59] = (float)state->random_state;
        memcpy(trace + 60, &state->random_state, sizeof(state->random_state));
#endif
        synthesise(state, &model, pcm + half * 80);
    }
    memcpy(state->previous_lsp, current_lsp, sizeof(current_lsp));
    state->previous_wo = next_wo;
    state->previous_energy = next_energy;
    state->previous_voiced = params.voiced[1];
    return 0;
}
