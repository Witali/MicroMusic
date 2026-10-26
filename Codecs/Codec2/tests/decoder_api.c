#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "codec2_decoder.h"

int main(int argc, char **argv) {
    assert(argc == 3);
    static codec2_decoder state[2];
    static unsigned char snapshot[sizeof(codec2_decoder)];
    unsigned char packets[2][16][8];
    int16_t expected[2][16][160], output[160];
    for (int stream = 0; stream < 2; ++stream) {
        FILE *file = fopen(argv[stream + 1], "rb");
        assert(file && fread(packets[stream], 8, 16, file) == 16);
        assert(!fclose(file));
    }
    memset(output, 0x5a, sizeof(output));
    int16_t saved[160];
    memcpy(saved, output, sizeof(saved));
    assert(codec2_decoder_decode(&state[0], packets[0][0], 8, output) == -1);
    assert(!memcmp(saved, output, sizeof(saved)));
    assert(codec2_decoder_init(NULL) == -1);
    assert(!codec2_decoder_init(&state[0]));
    memcpy(snapshot, &state[0], sizeof(snapshot));
    for (size_t size = 0; size <= 16; ++size) {
        if (size == 8) continue;
        assert(codec2_decoder_decode(&state[0], packets[0][0], size, output) == -1);
        assert(!memcmp(snapshot, &state[0], sizeof(snapshot)));
        assert(!memcmp(saved, output, sizeof(saved)));
    }
    assert(codec2_decoder_decode(NULL, packets[0][0], 8, output) == -1);
    assert(codec2_decoder_decode(&state[0], NULL, 8, output) == -1);
    assert(codec2_decoder_decode(&state[0], packets[0][0], 8, NULL) == -1);
    assert(!memcmp(snapshot, &state[0], sizeof(snapshot)));
    assert(!memcmp(saved, output, sizeof(saved)));
    for (int stream = 0; stream < 2; ++stream) {
        assert(!codec2_decoder_init(&state[stream]));
        for (int frame = 0; frame < 16; ++frame)
            assert(!codec2_decoder_decode(&state[stream], packets[stream][frame], 8, expected[stream][frame]));
    }
    for (int stream = 0; stream < 2; ++stream) assert(!codec2_decoder_init(&state[stream]));
    for (int frame = 0; frame < 16; ++frame)
        for (int stream = 0; stream < 2; ++stream) {
            assert(!codec2_decoder_decode(&state[stream], packets[stream][frame], 8, output));
            assert(!memcmp(output, expected[stream][frame], sizeof(output)));
        }
    puts("PASS: invalid calls preserve state/output; reinitialization and interleaved instances reproduce PCM");
    return 0;
}
