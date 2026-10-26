/* LGPL-2.1. Format definitions: original Codec2 1.2.0, see pinned vendor sources. */
#include "codec2_3200.h"

static uint8_t take_gray(const uint8_t *packet, uint8_t *position, uint8_t width) {
    uint8_t field = 0;
    do {
        uint8_t at = (*position)++;
        field = (uint8_t)((field << 1) | ((packet[at >> 3] >> (7 - (at & 7))) & 1));
    } while (--width);
    field ^= (uint8_t)(field >> 1);
    field ^= (uint8_t)(field >> 2);
    field ^= (uint8_t)(field >> 4);
    return field;
}

int codec2_3200_unpack(const uint8_t *packet, size_t length, codec2_3200_params *out) {
    uint8_t bit = 0;
    uint16_t frequency = 0;
    if (!packet || !out || length != 8) return -1;
    out->voiced[0] = take_gray(packet, &bit, 1);
    out->voiced[1] = take_gray(packet, &bit, 1);
    out->pitch_index = take_gray(packet, &bit, 7);
    out->energy_index = take_gray(packet, &bit, 5);
    for (uint8_t i = 0; i != 10; ++i) {
        uint8_t index = take_gray(packet, &bit, 5);
        out->lspd_index[i] = index;
        /* All ten pinned scalar codebooks are exact multiples of 25 Hz. */
        frequency += (i >= 3 && i <= 5 && index >= 8) ? 2 * index - 6 : index + 1;
        out->lsp_25hz[i] = frequency;
    }
    return 0;
}
