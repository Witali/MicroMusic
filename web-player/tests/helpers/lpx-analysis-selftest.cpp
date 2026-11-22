// Exercise private analysis/silence seams without exports in production WASM.
#include "../../lpx/native/encoder.cpp"
#if !LPX_ENCODER_FAST_SILENCE
#error Build this harness with the exact silent-block path enabled
#endif

extern "C" int lpx_silence_selftest() {
    if (!enc_reserve(1280)) return -1;
    uint32_t seed = 0x85a93b41;
    auto random = [&seed]() -> uint32_t { seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5; return seed; };
    const int profiles[] = {4, 6};
    int checks = 0;
    for (int profile : profiles) for (int pattern = 0; pattern < 3; ++pattern) {
        mode = profile;
        for (int j = 0; j < 1280; ++j) source[j] = pattern == 0 ? 0 : pattern == 1 ? int(random() % 3) - 1 : (j & 1 ? 32767 : -32768);
        for (int j = 0; j < 64; ++j) for (int k = 0; k < 10; ++k) coefficients[j][k] = int(random() % 12001) - 6000;
        // All eight possible 160-sample block alignments in the 256-slot ring.
        for (block = 0; block < 8; ++block) {
            state = {};
            for (int k = 0; k < 256; ++k) state.ring[k] = int(random() % 64) - 32;
            const int start = block * 160;
            State reference;
            searchBlock(reference, 0, 18, 0, true);
            int16_t referencePcm[160]; int referencePulses[8][2];
            memcpy(referencePcm, expected + start, sizeof(referencePcm));
            memcpy(referencePulses, pulses + start / 20, sizeof(referencePulses));
            commitSilentBlock(start);
            if (memcmp(&state, &reference, sizeof(State))) return -2;
            if (memcmp(referencePcm, expected + start, sizeof(referencePcm))) return -3;
            if (memcmp(referencePulses, pulses + start / 20, sizeof(referencePulses))) return -4;
            ++checks;
        }
    }
    return checks;
}
