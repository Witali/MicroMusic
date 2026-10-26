/* Scalar float transforms; no mutable FFT config and no heap. */
#ifndef MICROMUSIC_CODEC2_COMPACT_FFT_H
#define MICROMUSIC_CODEC2_COMPACT_FFT_H
typedef struct { float r, i; } compact_complex;
typedef union {
    compact_complex frequency[257];
    float time[514];
} compact_transform;

void compact_forward_lpc(compact_transform *buffer, const float coefficients[11]);
compact_complex compact_sparse_lpc_bin(const float coefficients[11], unsigned bin);
/* k=1..128, outputs for k and 256-k; k=128's original aliased bin uses negative. */
void compact_sparse_lpc_pair(const float coefficients[11], unsigned k,
                             compact_complex *positive, compact_complex *negative);
void compact_inverse(compact_transform *buffer);
float compact_window_value(unsigned index);
#endif
