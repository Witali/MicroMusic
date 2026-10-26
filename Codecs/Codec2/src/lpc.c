/* LGPL-2.1. Derived polynomial identity from original Codec2 lsp.c, David Rowe.
 * Original notices/license are retained in vendor/codec2-1.2.0/src/lsp.c.
 * This implementation multiplies the five second-order factors explicitly.
 */
#include "codec2_lpc.h"
#include "table_access.h"
#include "cosine_q15.inc"

static int32_t cosine_q15(uint16_t position) {
    uint16_t phase = position % 640;
    uint8_t negative = 0;
    if (phase > 320) phase = 640 - phase;
    if (phase > 160) {
        phase = 320 - phase;
        negative = 1;
    }
    int32_t magnitude = CODEC2_TABLE_WORD(codec2_cosine_quarter_q15, phase);
    return negative ? -magnitude : magnitude;
}

static int64_t rounded_product(int32_t coefficient, int32_t cosine) {
    int64_t value = (int64_t)coefficient * (2 * cosine);
    /* Shift non-negative magnitudes only; avoid implementation-defined signed >>. */
    return value < 0 ? -((-value + 16384) >> 15) : (value + 16384) >> 15;
}

static void factor(int32_t polynomial[11], uint8_t degree, int32_t cosine) {
    for (uint8_t j = degree; j != 0; --j) {
        int64_t value = (int64_t)polynomial[j] - rounded_product(polynomial[j - 1], cosine);
        if (j >= 2) value += polynomial[j - 2];
        polynomial[j] = (int32_t)value;
    }
}

void codec2_lsp_to_lpc_q23(const uint16_t lsp_12p5hz[10], int32_t coefficients[11]) {
    int32_t p[11], q[11];
    for (uint8_t i = 0; i != 11; ++i) p[i] = q[i] = 0;
    p[0] = q[0] = INT32_C(8388608);
    for (uint8_t i = 0; i != 5; ++i) {
        factor(p, (uint8_t)(2 * i + 2), cosine_q15(lsp_12p5hz[2 * i]));
        factor(q, (uint8_t)(2 * i + 2), cosine_q15(lsp_12p5hz[2 * i + 1]));
    }
    coefficients[0] = INT32_C(8388608);
    for (uint8_t i = 1; i != 11; ++i) {
        int64_t sum = (int64_t)p[i] + p[i - 1] + q[i] - q[i - 1];
        coefficients[i] = (int32_t)(sum / 2);  /* C99 truncation toward zero. */
    }
}
