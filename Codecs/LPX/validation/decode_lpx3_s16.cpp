// Host inspection driver for the original LPX3 v7 core, which only exposes PWM.
// Include its unchanged implementation in this single translation unit with
// state visibility for measurement; no modified header or MCU backend is made.
#include <stdint.h>
#include <vector>
#include <fstream>
#include <iterator>
#define private public
#include "../01_ACTIVE_Q0_CODEC/src/Lpx3AvrCore.cpp"
#undef private

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::ifstream input(argv[1], std::ios::binary);
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    if (data.size() > 65535) return 3;
    Lpx3AvrCore core;
    if (!core.begin(data.data(), (uint16_t)data.size())) return 4;
    std::ofstream out(argv[2], std::ios::binary);
    uint8_t pwm;
    int16_t previous_clip = 0;
    while (core.next(pwm)) {
        const int16_t clipped = core.prevBright_;
        const int32_t b = Lpx3AvrCore::clamp((int32_t)clipped -
            (((int32_t)(int16_t)core.brightQ14_ * previous_clip) >> 14), -16384, 16384);
        previous_clip = clipped;
        const uint16_t s = (uint16_t)Lpx3AvrCore::clamp(b * 2, -32768, 32767);
        const char bytes[2] = {(char)(s & 255), (char)(s >> 8)};
        out.write(bytes, 2);
    }
    return core.finished() && out.good() ? 0 : 5;
}
