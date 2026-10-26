/* Tests the portable/archived C against unmodified upstream unpack and codebooks.
 * LGPL-2.1; see vendor/codec2-1.2.0/COPYING.
 */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "codec2_3200.h"
#include "defines.h"
#include "quantise.h"

extern void codec2_params_3200(const uint8_t packet[8], codec2_3200_params *out);

static void oracle(const uint8_t packet[8], codec2_3200_params *out) {
    unsigned bit = 0;
    int indexes[10];
    float radians[10];
    out->voiced[0] = (uint8_t)unpack(packet, &bit, 1);
    out->voiced[1] = (uint8_t)unpack(packet, &bit, 1);
    out->pitch_index = (uint8_t)unpack(packet, &bit, 7);
    out->energy_index = (uint8_t)unpack(packet, &bit, 5);
    for (int i = 0; i < 10; ++i) {
        indexes[i] = unpack(packet, &bit, lspd_bits(i));
        out->lspd_index[i] = (uint8_t)indexes[i];
    }
    assert(bit == 64);
    decode_lspds_scalar(radians, indexes, 10);
    float frequency = 0;
    for (int i = 0; i < 10; ++i) {
        frequency += lsp_cbd[i].cb[indexes[i]];
        out->lsp_25hz[i] = (uint16_t)lroundf(frequency / 25.0f);
        assert(fabsf(radians[i] - (float)(PI / 160.0 * out->lsp_25hz[i])) < 0.000002f);
    }
}

int main(int argc, char **argv) {
    assert(argc == 3);
    FILE *input = fopen(argv[1], "rb"), *output = fopen(argv[2], "wb");
    assert(input && output);
    uint8_t packet[8];
    codec2_3200_params actual, expected, archived;
    memset(&actual, 0xa5, sizeof(actual));
    expected = actual;
    for (size_t len = 0; len <= 16; ++len) {
        if (len == 8) continue;
        assert(codec2_3200_unpack(packet, len, &actual) == -1);
        assert(memcmp(&actual, &expected, sizeof(actual)) == 0);
    }
    assert(codec2_3200_unpack(NULL, 8, &actual) == -1);
    assert(codec2_3200_unpack(packet, 8, NULL) == -1);
    assert(memcmp(&actual, &expected, sizeof(actual)) == 0);
    unsigned count = 0;
    size_t got;
    while ((got = fread(packet, 1, 8, input)) != 0) {
        assert(got == 8);
        memset(&expected, 0, sizeof(expected));
        memset(&archived, 0, sizeof(archived));
        memset(&actual, 0, sizeof(actual));
        oracle(packet, &expected);
        codec2_params_3200(packet, &archived);
        assert(codec2_3200_unpack(packet, 8, &actual) == 0);
        assert(memcmp(&actual, &expected, sizeof(actual)) == 0);
        assert(memcmp(&archived, &expected, sizeof(actual)) == 0);
        /* Explicit little-endian wire record independent of struct padding. */
        assert(fwrite(&actual, 1, 14, output) == 14);
        for (int i = 0; i < 10; ++i) {
            assert(fputc(actual.lsp_25hz[i] & 255, output) != EOF);
            assert(fputc(actual.lsp_25hz[i] >> 8, output) != EOF);
        }
        ++count;
    }
    assert(!ferror(input));
    assert(fclose(input) == 0 && fclose(output) == 0);
    printf("PASS: %u packets, portable C = archived R3 = pinned upstream; invalid lengths/nulls checked\n", count);
    return 0;
}
