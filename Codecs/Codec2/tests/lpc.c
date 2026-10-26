/* Upstream float oracle comparison and explicit LE integer records. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include "codec2_lpc.h"
#include "defines.h"
#include "lsp.h"

int main(int argc, char **argv) {
    assert(argc == 3);
    FILE *input = fopen(argv[1], "rb"), *output = fopen(argv[2], "wb");
    assert(input && output);
    unsigned count = 0;
    double maximum = 0;
    unsigned char bytes[20];
    size_t got;
    while ((got = fread(bytes, 1, 20, input)) != 0) {
        assert(got == 20);
        uint16_t positions[10];
        float radians[10], reference[11];
        int32_t actual[11];
        for (int i = 0; i < 10; ++i) {
            positions[i] = bytes[2 * i] | ((uint16_t)bytes[2 * i + 1] << 8);
            radians[i] = (float)(positions[i] * (PI / 320.0));
        }
        lsp_to_lpc(radians, reference, 10);
        codec2_lsp_to_lpc_q23(positions, actual);
        assert(actual[0] == 8388608);
        for (int i = 0; i < 11; ++i) {
            double error = fabs(actual[i] / 8388608.0 - reference[i]);
            if (error > maximum) maximum = error;
            assert(error < 0.025); /* Includes highly clustered/crossing stress roots. */
            uint32_t word = (uint32_t)actual[i];
            for (int byte = 0; byte < 4; ++byte) assert(fputc((word >> (8 * byte)) & 255, output) != EOF);
        }
        ++count;
    }
    assert(!ferror(input));
    assert(fclose(input) == 0 && fclose(output) == 0);
    printf("{\"vectors\":%u,\"max_absolute_lpc_error_vs_upstream\":%.9g,\"allowed_absolute_error\":0.025}\n", count, maximum);
    return 0;
}
