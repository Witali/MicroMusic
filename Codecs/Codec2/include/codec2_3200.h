/* Codec2 mode-3200 parameter front end. LGPL-2.1; see vendor/codec2-1.2.0/COPYING.
 * Format reference: pinned Codec2 pack.c and quantise.c. No waveform synthesis yet.
 */
#ifndef MICROMUSIC_CODEC2_3200_H
#define MICROMUSIC_CODEC2_3200_H
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint8_t voiced[2];
    uint8_t pitch_index;
    uint8_t energy_index;
    uint8_t lspd_index[10];
    uint16_t lsp_25hz[10];
} codec2_3200_params;

/* Exactly eight packet bytes; input/output must not overlap.
 * Returns 0 on success, -1 for null pointers or a wrong length, leaving out intact.
 * Raw codebook frequencies are retained, including out-of-band random patterns.
 * Portable C is the only backend; no hardware memory addresses or global state.
 */
int codec2_3200_unpack(const uint8_t *packet, size_t length, codec2_3200_params *out);
#endif
