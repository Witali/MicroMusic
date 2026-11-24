// Exercise private analysis/silence seams without exports in production WASM.
#include "LpxEncoder.cpp"
#if !LPX_ENCODER_FAST_SILENCE
#error Build this harness with the exact silent-block path enabled
#endif

extern "C" int lpx_silence_selftest() {
    auto& kernel=lpx::defaultSeedEncoder();
    if (!enc_reserve(1280)) return -1;
    uint32_t seed = 0x85a93b41;
    auto random = [&seed]() -> uint32_t { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed; };
    const int profiles[] = {4, 6};
    int checks = 0;
    for (int profile : profiles) for (int pattern = 0; pattern < 3; ++pattern) {
        kernel.mode = profile;
        for (int j = 0; j < 1280; ++j) kernel.source[j] = pattern == 0 ? 0 : pattern == 1 ? int(random() % 3) - 1 : (j & 1 ? 32767 : -32768);
        for (int j = 0; j < 64; ++j) for (int k = 0; k < 10; ++k) kernel.coefficients[j][k] = int(random() % 12001) - 6000;
        // All eight possible 160-sample block alignments in the 256-slot ring.
        for (kernel.block = 0; kernel.block < 8; ++kernel.block) {
            kernel.state = {};
            for (int k = 0; k < 256; ++k) kernel.state.ring[k] = int(random() % 64) - 32;
            const int start = kernel.block * 160;
            State reference;
            kernel.searchBlock(reference, 0, 18, 0, true);
            int16_t referencePcm[160]; int referencePulses[8][2];
            memcpy(referencePcm, kernel.expected + start, sizeof(referencePcm));
            memcpy(referencePulses, kernel.pulses + start / 20, sizeof(referencePulses));
            kernel.commitSilentBlock(start);
            if (memcmp(&kernel.state, &reference, sizeof(State))) return -2;
            if (memcmp(referencePcm, kernel.expected + start, sizeof(referencePcm))) return -3;
            if (memcmp(referencePulses, kernel.pulses + start / 20, sizeof(referencePulses))) return -4;
            ++checks;
        }
    }
    return checks;
}

extern "C" int lpx_analysis_selftest() {
    auto& kernel=lpx::defaultSeedEncoder();
    kernel.prepareAnalysis();
    int checks = 0;
    for (int j = 0; j < 256; ++j) {
        const double reference = .54 - .46 * cos(2 * pi * j / 255);
        if (memcmp(&reference, &analysisTables().window[j], sizeof(double))) return -1;
        ++checks;
    }
    for (int part = 0; part < 2; ++part) for (int grid = 0; grid <= 640; ++grid) {
        const double w = grid ? pi * grid / 641 : 1e-6;
        for (int k = 0; k <= 10; ++k) {
            const double reference = part ? sin(w * (5.5 - k)) : cos(w * (5.5 - k));
            if (memcmp(&reference, &analysisTables().rootGrid[part][grid][k], sizeof(double))) return -2;
            ++checks;
        }
        for (int pattern = 0; pattern < 5; ++pattern) {
            double a[11];
            for (int k = 0; k <= 10; ++k) a[k] = pattern == 0 ? (k == 0 ? 1 : 0)
                : pattern == 1 ? 1 : pattern == 2 ? (k & 1 ? -1 : 1)
                : pattern == 3 ? (k - 5) * .123456789 : (k & 1 ? -1 : 1) * (k + 1) * 1023.987654321;
            const double reference = rootValue(a, w, part), actual = gridRootValue(a, grid, part);
            if (memcmp(&reference, &actual, sizeof(double))) return -3;
            ++checks;
        }
    }
    return checks;
}
