/* Generated experiment: optional LPC postfilter and its bass boost disabled. */
/* Generated explicit canonical LPC boundaries; vendor and frozen sources remain intact. */
#include "fixed_analysis.h"
#include "lpc_math.h"
#define compact_forward_lpc codec2_analysis_forward
/* Candidate: fixed weighted LPC spectrum; other analysis/phase stages remain float. */
/* LGPL-2.1. Derived from Codec2 1.2.0, David Rowe; original notices in vendor/.
 * All mode-3200 stages retained. Memory changes: ROM FFT tables, one in-place
 * transform, sparse exact weighting spectrum, and only live OLA history.
 */
#include "codec2_hybrid.h"
#include "fixed_inverse.h"
#include "codec2_3200.h"
#include "compact_fft.h"
#include "decoder_control.h"
#include "lsp.h"
#include <float.h>
#include <math.h>
#include <string.h>

#if FLT_RADIX != 2 || FLT_MANT_DIG != 24
#error This profile requires IEEE binary32
#endif
typedef char compact_float_size[(sizeof(float) == 4) ? 1 : -1];

typedef struct {
    float wo;
    int harmonics;
    int voiced;
} compact_model;

static unsigned random_value(codec2_compact *state) {
    state->random_state = state->random_state * UINT32_C(1103515245) + UINT32_C(12345);
    return (unsigned)((state->random_state >> 16) & 32767);
}

int codec2_hybrid_init(codec2_compact *state) {
    if (!state) return -1;
    memset(state, 0, sizeof(*state));
    state->previous_wo = TWO_PI / 160;
    state->previous_energy = 1;
    state->random_state = 1;
    for (int i = 0; i < 10; ++i) state->previous_lsp[i] = codec2_lpc_initial_angle(i);
    state->initialized = 1;
    return 0;
}

/* Phase does not depend on LPC amplitudes. Run this while analysis bins still
 * exist, then reuse their memory for postfilter powers. RNG ordering is retained:
 * background/noise randomization still runs only after amplitude reconstruction.
 */
static void initial_phases(codec2_compact *state, compact_model *model, compact_transform *analysis) {
    state->excitation_phase += model->wo * 80;
    state->excitation_phase -= TWO_PI * floorf(state->excitation_phase / TWO_PI + 0.5);
    float r = TWO_PI / 512;
    int power_cursor = 0;
    for (int m = 1; m <= model->harmonics; ++m) {
        int bin = (int)(m * model->wo / r + 0.5);
        float angle = model->voiced ? state->excitation_phase * m
                                   : (float)(TWO_PI * (float)random_value(state) / 32767);
        float real = cosf(angle), imag = sinf(angle);
        float hr = analysis->frequency[bin].r, hi = -analysis->frequency[bin].i;
        float ar = hr * real - hi * imag;
        float ai = hi * real + hr * imag;
        float phase = atan2f(ai, ar + 1E-12);
        /* At least 3.2 FFT bins per harmonic: m is behind every future phase
         * read. Convert old bins to power before borrowing their imag slots.
         */
        int last = bin < 256 ? bin : 255;
        while (power_cursor <= last) {
            compact_complex value = analysis->frequency[power_cursor];
            analysis->frequency[power_cursor].r = 1.0 / (value.r * value.r + value.i * value.i + 1E-6);
            ++power_cursor;
        }
        analysis->frequency[m].i = phase;
    }
    while (power_cursor < 256) {
        compact_complex value = analysis->frequency[power_cursor];
        analysis->frequency[power_cursor].r = 1.0 / (value.r * value.r + value.i * value.i + 1E-6);
        ++power_cursor;
    }
}

/* Upstream aks_to_M2 with pf=0: scale the unmodified power by E.
 * The separate phase/background postfilter remains enabled. */
static void amplitudes(float ak[11], compact_model *model, float energy, compact_transform *buffer) {
    (void)ak;
    for (unsigned i = 0; i < 256; ++i) buffer->frequency[i].r *= energy;
    float r = TWO_PI / 512;
    for (int m = 1; m <= model->harmonics; ++m) {
        int first = band_boundary(2 * m - 1, model->wo, r);
        int last = band_boundary(2 * m + 1, model->wo, r);
        if (last > 256) last = 256;
        float sum = 0;
        for (int i = first; i < last; ++i) sum += buffer->frequency[i].r;
        /* m < first: these power bins have already been consumed. */
        buffer->frequency[m].r = sqrtf(sum);
    }
    if (model->wo < (PI * 150.0 / 4000)) buffer->frequency[1].r *= 0.032;
}

static void background_filter(codec2_compact *state, compact_model *model, compact_transform *buffer) {
    float energy = 1E-12;
    for (int m = 1; m <= model->harmonics; ++m) energy += buffer->frequency[m].r * buffer->frequency[m].r;
    energy = 10.0 * log10f(energy / model->harmonics);
    if (energy < 40.0 && !model->voiced)
        state->background = state->background * (1.0 - 0.1) + energy * 0.1;
    float threshold = POW10F((state->background + 6.0) / 20.0);
    if (model->voiced)
        for (int m = 1; m <= model->harmonics; ++m)
            if (buffer->frequency[m].r < threshold)
                buffer->frequency[m].i = (TWO_PI / 32767) * (float)random_value(state);
}

static void synthesise(codec2_compact *state, compact_model *model, compact_transform *buffer, int16_t *pcm) {
    int clear = 256;
    /* Scatter rightward in descending harmonic order, preserving unread
     * amplitude/phase pairs at lower indices and clearing only dead slots.
     */
    for (int m = model->harmonics; m >= 1; --m) {
        float amplitude = buffer->frequency[m].r, phase = buffer->frequency[m].i;
        int bin = synthesis_bin(m * model->wo);
        if (bin > 255) bin = 255;
        while (clear > bin) {
            buffer->frequency[clear].r = buffer->frequency[clear].i = 0;
            --clear;
        }
        buffer->frequency[bin].r = amplitude * cosf(phase);
        buffer->frequency[bin].i = amplitude * sinf(phase);
        clear = bin - 1;
    }
    while (clear >= 0) {
        buffer->frequency[clear].r = buffer->frequency[clear].i = 0;
        --clear;
    }
    codec2_fixed_inverse(buffer);
    for (unsigned i = 0; i < 79; ++i) {
        buffer->time[433 + i] = state->tail[i] + buffer->time[433 + i] * compact_window_value(i);
        state->tail[i] = buffer->time[1 + i] * compact_window_value(80 + i);
    }
    /* Index 512 is unused after inverse transform, available for the 80th head
     * sample. Original Sn_[159] is never read by the next OLA shift.
     */
    buffer->time[512] = buffer->time[0] * compact_window_value(79);
    float maximum = 0;
    for (unsigned i = 433; i <= 512; ++i)
        if (buffer->time[i] > maximum) maximum = buffer->time[i];
    float over = maximum / 30000.0;
    if (over > 1.0) {
        float gain = 1.0 / (over * over);
        for (unsigned i = 433; i <= 512; ++i) buffer->time[i] *= gain;
    }
    for (unsigned i = 0; i < 80; ++i) {
        float sample = buffer->time[433 + i];
        pcm[i] = sample > 32767.0 ? 32767 : sample < -32767.0 ? -32767 : (int16_t)sample;
    }
}

int codec2_hybrid_decode(codec2_compact *state, const uint8_t *packet, size_t length, int16_t *pcm) {
    if (!state || !state->initialized || !packet || !pcm || length != 8) return -1;
    codec2_3200_params params;
    codec2_3200_unpack(packet, length, &params);
    float current_lsp[10], ak[11];
    float wo_min = TWO_PI / 160, wo_max = TWO_PI / 20;
    float step = (wo_max - wo_min) / 128;
    float next_wo = wo_min + step * params.pitch_index;
    float energy_db = -10.0 + (50.0f / 32) * params.energy_index;
    float next_energy = POW10F(energy_db / 10.0);
    for (int i = 0; i < 10; ++i) current_lsp[i] = codec2_lpc_grid_angle(params.lsp_25hz[i]);
    for (int half = 0; half < 2; ++half) {
        compact_model model;
        compact_transform buffer;
        model.voiced = params.voiced[half]; model.wo = next_wo;
        float energy = next_energy;
        if (!half) {
            if (model.voiced && !state->previous_voiced && !params.voiced[1]) model.voiced = 0;
            if (model.voiced) {
                if (state->previous_voiced && params.voiced[1]) model.wo = (1.0 - 0.5) * state->previous_wo + 0.5f * next_wo;
                if (state->previous_voiced && !params.voiced[1]) model.wo = state->previous_wo;
            } else model.wo = wo_min;
            energy = sqrtf(state->previous_energy * next_energy);
            for (int i = 0; i < 10; ++i)
                state->previous_lsp[i] = (1.0 - 0.5) * state->previous_lsp[i] + 0.5f * current_lsp[i];
        }
        model.harmonics = harmonic_count(model.wo);
        if (model.harmonics < 1 || model.harmonics > 80) return -2;
        codec2_canonical_lsp_to_lpc(half ? current_lsp : state->previous_lsp, ak, 10);
        compact_forward_lpc(&buffer, ak);
        initial_phases(state, &model, &buffer);
        amplitudes(ak, &model, energy, &buffer);
        background_filter(state, &model, &buffer);
        synthesise(state, &model, &buffer, pcm + half * 80);
    }
    memcpy(state->previous_lsp, current_lsp, sizeof(current_lsp));
    state->previous_wo = next_wo; state->previous_energy = next_energy;
    state->previous_voiced = params.voiced[1];
    return 0;
}
