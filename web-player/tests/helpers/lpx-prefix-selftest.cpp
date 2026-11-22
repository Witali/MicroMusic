// Test the private search seam without adding exports to the shipped module.
#include "../../lpx/native/encoder.cpp"
#if !LPX_ENCODER_REUSE_PREFIX
#error Build this harness with prefix reuse enabled
#endif

extern "C" int lpx_prefix_selftest() {
    if (!enc_reserve(1024)) return -1;
    uint32_t seed = 0x963e45a1;
    auto random = [&seed]() -> uint32_t { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed; };
    const int cursors[] = {0, 240, 260}; // Include ring wrap inside a subframe.
    const int lags[] = {18, 19, 20, 21, 145}, gains[] = {0, 2, 14}, scales[] = {0, 6, 10, 31};
    int checks = 0;
    for (int pattern = 0; pattern < 3; ++pattern) {
        State initial = {};
        for (int j = 0; j < 1024; ++j) source[j] = pattern == 0 ? 0 : pattern == 1 ? int(random() & 65535) - 32768 : (j & 1 ? 32767 : -32768);
        for (int j = 0; j < 64; ++j) for (int k = 0; k < 10; ++k) coefficients[j][k] = pattern ? int(random() % 12001) - 6000 : 0;
        if (pattern) {
            initial.dd = int(random() % 65535) - 32767;
            for (int k = 0; k < 10; ++k) initial.h[k] = int(random() % 65535) - 32767;
            for (int k = 0; k < 256; ++k) initial.ring[k] = int(random() % 64) - 32;
        }
        for (int cursor : cursors) for (int lag : lags) for (int gain : gains) for (int scale : scales) {
            State full, reused, scratch;
            trial20(scratch, initial, cursor, scale, lag, gain, 20, 0, false, HUGE_VAL, false, true);
            for (int pos = 0; pos < 20; ++pos) for (int amp = -8; amp <= 8; ++amp) {
                const double expectedLoss = trial20(full, initial, cursor, scale, lag, gain, pos, amp, false);
                const double actualLoss = trial20(reused, initial, cursor, scale, lag, gain, pos, amp, false, HUGE_VAL, true);
                if (actualLoss != expectedLoss) return -2;
                if (memcmp(&full, &reused, sizeof(State))) return -3;
                ++checks;
                const double bounds[] = {0, expectedLoss / 2, expectedLoss, expectedLoss + 1};
                for (double bound : bounds) {
                    const double before = trial20(full, initial, cursor, scale, lag, gain, pos, amp, false, bound);
                    const double after = trial20(reused, initial, cursor, scale, lag, gain, pos, amp, false, bound, true);
                    // Aborted partial losses/states may differ; only a winner
                    // may be used, and every possible winner must be exact.
                    if ((before < bound) != (after < bound)) return -4;
                    if (after < bound && (after != before || memcmp(&full, &reused, sizeof(State)))) return -5;
                    ++checks;
                }
            }
        }
    }
    return checks;
}
