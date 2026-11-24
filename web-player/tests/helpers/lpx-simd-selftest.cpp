#include "LpxEncoder.cpp"
#if !LPX_ENCODER_HAS_SIMD_SEARCH
#error Build this harness with the explicit WASM SIMD search enabled
#endif
extern "C" int lpx_simd_selftest() {
    auto& kernel=lpx::defaultSeedEncoder();
    if (!enc_reserve(1024)) return -1;
    uint32_t seed = 0x675da431;
    auto random = [&seed]() -> uint32_t { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed; };
    const int cursors[] = {0, 240, 260}, lags[] = {18, 19, 20, 21, 145}, gains[] = {0, 2, 14}, scales[] = {0, 6, 10, 31};
    int checks = 0;
    for (int pattern = 0; pattern < 3; ++pattern) {
        State initial = {};
        for (int j = 0; j < 1024; ++j) kernel.source[j] = pattern == 0 ? 0 : pattern == 1 ? int(random() & 65535) - 32768 : (j & 1 ? 32767 : -32768);
        for (int j = 0; j < 64; ++j) for (int k = 0; k < 10; ++k) kernel.coefficients[j][k] = pattern == 0 ? 0
            : pattern == 1 ? int(random() % 12001) - 6000 : (k & 1 ? 32767 : -32767);
        if (pattern) {
            initial.dd = int(random() % 65535) - 32767;
            for (int k = 0; k < 10; ++k) initial.h[k] = int(random() % 65535) - 32767;
            for (int k = 0; k < 256; ++k) initial.ring[k] = int(random() % 64) - 32;
        }
        for (int cursor : cursors) for (int lag : lags) for (int gain : gains) for (int scale : scales) {
            State scratch;
            kernel.trial20(scratch, initial, cursor, scale, lag, gain, 20, 0, false, HUGE_VAL, false, true);
            for (int profile = 4; profile <= 6; profile += 2) for (int pos = 0; pos < 20; ++pos) {
                for (int ai = 0; ai < (profile == 4 ? 2 : 16); ai += profile == 4 ? 2 : 4) {
                    int amplitudes[4]; double full[4], actual[4];
                    const int n = profile == 4 ? 2 : 4;
                    for (int lane = 0; lane < 4; ++lane) {
                        amplitudes[lane] = profile == 4 ? (lane & 1 ? 8 : -8) : ai + lane - 8;
                        full[lane] = kernel.trial20(scratch, initial, cursor, scale, lag, gain, pos, amplitudes[lane], false);
                    }
                    const double bounds[] = {0, full[0] / 2, full[0], full[0] + 1, HUGE_VAL};
                    for (double bound : bounds) {
                        const State& prefix = kernel.prefixState[pos];
                        lpxTrial4(actual, prefix.h, prefix.ring, prefix.dd, kernel.coefficients[cursor / 20], kernel.source + cursor,
                            cursor, steps[scale * 8], lag, gain, pos, amplitudes, kernel.prefixLoss[pos], bound, true);
                        for (int lane = 0; lane < n; ++lane) {
                            if ((full[lane] < bound) != (actual[lane] < bound)) return -2;
                            if (full[lane] < bound && full[lane] != actual[lane]) return -3;
                            ++checks;
                        }
                    }
                }
            }
        }
    }
    return checks;
}
