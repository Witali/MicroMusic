/* Generated original upstream oracle with its supported LPC postfilter disabled. */
/* Oracle: original mode-3200 decode/synthesis function bodies, original KISS FFT.
 * Decoder-only initialization reproduces codec2_create's used state; no encoder.
 * LGPL-2.1, pinned upstream sources/notices retained in vendor/codec2-1.2.0.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "codec2_internal.h"
#include "sine.h"
#include "quantise.h"
extern void codec2_decode_3200(struct CODEC2 *, short *, const unsigned char *);

int main(int argc, char **argv) {
    assert(argc == 3);
    struct CODEC2 *c2 = calloc(1, sizeof(*c2));
    assert(c2);
    c2->mode = 0;
    c2->c2const = c2const_create(8000, N_S);
    c2->Fs = 8000;
    c2->n_samp = 80;
    c2->fftr_fwd_cfg = codec2_fftr_alloc(512, 0, NULL, NULL);
    c2->fftr_inv_cfg = codec2_fftr_alloc(512, 1, NULL, NULL);
    assert(c2->fftr_fwd_cfg && c2->fftr_inv_cfg);
    c2->Pn = calloc(160, sizeof(float));
    c2->Sn_ = calloc(160, sizeof(float));
    assert(c2->Pn && c2->Sn_);
    make_synthesis_window(&c2->c2const, c2->Pn);
    c2->prev_model_dec.Wo = TWO_PI / c2->c2const.p_max;
    c2->prev_model_dec.L = PI / c2->prev_model_dec.Wo;
    for (int i = 0; i < 10; ++i) c2->prev_lsps_dec[i] = i * PI / 11;
    c2->prev_e_dec = 1;
    c2->lpc_pf = c2->bass_boost = 0;
    c2->beta = LPCPF_BETA;
    c2->gamma = LPCPF_GAMMA;
    FILE *input = fopen(argv[1], "rb"), *output = fopen(argv[2], "wb");
    assert(input && output);
    unsigned char packet[8];
    short pcm[160];
    size_t got;
    while ((got = fread(packet, 1, 8, input))) {
        assert(got == 8);
        codec2_decode_3200(c2, pcm, packet);
        assert(fwrite(pcm, sizeof(short), 160, output) == 160);
    }
    assert(!ferror(input));
    assert(!fclose(input) && !fclose(output));
    codec2_fftr_free(c2->fftr_fwd_cfg); codec2_fftr_free(c2->fftr_inv_cfg);
    free(c2->Pn); free(c2->Sn_); free(c2);
    return 0;
}
