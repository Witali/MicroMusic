#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "codec2_decoder.h"

int main(int argc, char **argv) {
    assert(argc == 3 || argc == 4);
    static codec2_decoder state;
    assert(!codec2_decoder_init(&state));
    FILE *input = fopen(argv[1], "rb"), *output = fopen(argv[2], "wb");
    assert(input && output);
    unsigned char packet[8];
    int16_t pcm[160];
    size_t got;
#ifdef CODEC2_DECODER_TRACE
    extern float codec2_decoder_trace[2][64];
    FILE *trace = argc == 4 ? fopen(argv[3], "wb") : NULL;
#endif
    while ((got = fread(packet, 1, 8, input))) {
        assert(got == 8);
        assert(!codec2_decoder_decode(&state, packet, 8, pcm));
        assert(fwrite(pcm, sizeof(int16_t), 160, output) == 160);
#ifdef CODEC2_DECODER_TRACE
        if (trace) assert(fwrite(codec2_decoder_trace, sizeof(codec2_decoder_trace), 1, trace) == 1);
#endif
    }
    assert(!ferror(input));
    assert(!fclose(input) && !fclose(output));
#ifdef CODEC2_DECODER_TRACE
    if (trace) assert(!fclose(trace));
#endif
    printf("state=%u, fft=%u\n", (unsigned)sizeof(state), state.fft_bytes);
    return 0;
}
