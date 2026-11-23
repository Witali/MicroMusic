#pragma once

// Four independent pulse amplitudes at one position. No shared codec state is
// mutated; the selected candidate is replayed by the portable scalar trial.
#if LPX_ENCODER_SIMD_SEARCH && defined(__wasm__) && defined(__wasm_simd128__) && LPX_ENCODER_REUSE_PREFIX
#define LPX_ENCODER_HAS_SIMD_SEARCH 1
#include <wasm_simd128.h>

static inline v128_t lpxClip4(v128_t value, int low, int high) {
    return wasm_i32x4_min(wasm_i32x4_max(value, wasm_i32x4_splat(low)), wasm_i32x4_splat(high));
}
static void lpxTrial4(double result[4], const int history[10], const int ring[256], int previous,
    const int16_t co[10], const int16_t input[20], int cursor, int step, int lag, int gain,
    int pos, const int amplitudes[4], double prefixLoss, double bound, bool prune, int pre = 13926) {
    if (prune && prefixLoss >= bound) { for (int lane = 0; lane < 4; ++lane) result[lane] = prefixLoss; return; }
    v128_t h[10], excitation[2];
    for (int k = 0; k < 10; ++k) h[k] = wasm_i32x4_splat(history[k]);
    v128_t dd = wasm_i32x4_splat(previous), lo = wasm_f64x2_splat(prefixLoss), hi = lo;
    const v128_t limit = wasm_f64x2_splat(bound), gain4 = wasm_i32x4_splat(gain);
    const v128_t amp = wasm_v128_load(amplitudes), step4 = wasm_i32x4_splat(step);
    for (int j = pos; j < 20; ++j) {
        // Lags are 18..145: only generated samples 0/1 can feed back here.
        v128_t delayed = j >= lag && j - lag >= pos ? excitation[j - lag]
            : wasm_i32x4_splat(ring[(cursor + j - lag) & 255]);
        v128_t q = lpxClip4(wasm_i32x4_shr(wasm_i32x4_add(wasm_i32x4_mul(gain4, delayed), wasm_i32x4_splat(8)), 4), -32, 31);
        if (j == pos) q = lpxClip4(wasm_i32x4_add(q, amp), -32, 31);
        if (j < 2) excitation[j] = q;
        v128_t acc = wasm_i32x4_splat(0);
        for (int k = 0; k < 10; ++k) acc = wasm_i32x4_add(acc, wasm_i32x4_shr(wasm_i32x4_mul(wasm_i32x4_splat(co[k]), h[k]), 12));
        v128_t pred = lpxClip4(wasm_i32x4_sub(wasm_i32x4_mul(q, step4), acc), -32767, 32767);
        for (int k = 9; k; --k) h[k] = h[k - 1]; h[0] = pred;
        dd = lpxClip4(wasm_i32x4_add(pred, wasm_i32x4_shr(wasm_i32x4_mul(wasm_i32x4_splat(pre), dd), 14)), -32767, 32767);
        v128_t sample = lpxClip4(wasm_i32x4_mul(lpxClip4(dd, -16384, 16384), wasm_i32x4_splat(2)), -32768, 32767);
        v128_t delta = wasm_i32x4_sub(sample, wasm_i32x4_splat(input[j]));
        v128_t a = wasm_f64x2_convert_low_i32x4(delta);
        v128_t b = wasm_f64x2_convert_low_i32x4(wasm_i32x4_shuffle(delta, delta, 2, 3, 2, 3));
        lo = wasm_f64x2_add(lo, wasm_f64x2_mul(a, a));
        hi = wasm_f64x2_add(hi, wasm_f64x2_mul(b, b));
        if (prune && !wasm_v128_any_true(wasm_v128_or(wasm_f64x2_lt(lo, limit), wasm_f64x2_lt(hi, limit)))) break;
    }
    wasm_v128_store(result, lo); wasm_v128_store(result + 2, hi);
}
#else
#define LPX_ENCODER_HAS_SIMD_SEARCH 0
#endif
