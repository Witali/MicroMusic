#include <assert.h>
#include <stdio.h>
#include "codec2_compact.h"

int main(int argc, char **argv) {
    assert(argc == 3);
    static codec2_compact state;
    assert(!codec2_compact_init(&state));
    FILE *input = fopen(argv[1], "rb"), *output = fopen(argv[2], "wb");
    assert(input && output);
    uint8_t packet[8];
    int16_t pcm[160];
    size_t got;
    while ((got = fread(packet, 1, 8, input))) {
        assert(got == 8);
        assert(!codec2_compact_decode(&state, packet, 8, pcm));
        assert(fwrite(pcm, sizeof(int16_t), 160, output) == 160);
    }
    assert(!ferror(input));
    assert(!fclose(input) && !fclose(output));
    printf("compact state=%u\n", (unsigned)sizeof(state));
    return 0;
}
