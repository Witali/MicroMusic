// Independent native driver: intentionally uses the public core API directly.
#include "Lpx4HybridCore.h"
#include <cstdio>
#include <vector>
#include <stdint.h>
int main() {
    uint32_t bytes;
    while (fread(&bytes, 4, 1, stdin) == 1) {
        if (bytes > 100 * 1024 * 1024) return 1;
        std::vector<uint8_t> data(bytes);
        if (fread(data.data(), 1, bytes, stdin) != bytes) return 2;
        Lpx4HybridCore core;
        std::vector<int16_t> pcm;
#if LPX4_ENABLE_WIDE_V9
        const bool valid = core.beginWideV9(data.data(), bytes);
#else
        const bool valid = bytes <= 65535 && core.begin(data.data(), bytes);
#endif
        if (valid) {
            int16_t sample;
            while (core.nextS16(sample)) pcm.push_back(sample);
            if (core.error() || !core.finished() || core.produced() != pcm.size()) pcm.clear();
        }
        uint32_t size = pcm.size() * 2;
        fwrite(&size, 4, 1, stdout);
        if (size) fwrite(pcm.data(), 1, size, stdout);
    }
    return ferror(stdin) || ferror(stdout) ? 3 : 0;
}
