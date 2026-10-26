/* Offline table extraction from the pinned unmodified KISS FFT and Codec2 window.
 * KISS copyright/notices remain in the vendor files and generated table header.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "kiss_fftr.h"
#include "_kiss_fft_guts.h"
#include "defines.h"
#include "sine.h"

struct kiss_fftr_state {
    kiss_fft_cfg substate;
    kiss_fft_cpx *tmpbuf;
    kiss_fft_cpx *super_twiddles;
};

static void write_float(FILE *output, float value) {
    uint32_t bits;
    assert(sizeof(value) == sizeof(bits));
    memcpy(&bits, &value, sizeof(bits));
    for (int i = 0; i < 4; ++i) assert(fputc((bits >> (8 * i)) & 255, output) != EOF);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    FILE *output = fopen(argv[1], "wb");
    assert(output);
    kiss_fftr_cfg cfg = kiss_fftr_alloc(512, 0, NULL, NULL);
    assert(cfg && cfg->substate->nfft == 256);
    for (int i = 0; i < 256; ++i) {
        write_float(output, cfg->substate->twiddles[i].r);
        write_float(output, cfg->substate->twiddles[i].i);
    }
    for (int i = 0; i < 128; ++i) {
        write_float(output, cfg->super_twiddles[i].r);
        write_float(output, cfg->super_twiddles[i].i);
    }
    C2CONST constants;
    memset(&constants, 0, sizeof(constants));
    constants.n_samp = 80;
    constants.tw = 40;
    float window[160];
    make_synthesis_window(&constants, window);
    for (int i = 0; i < 160; ++i) write_float(output, window[i]);
    kiss_fftr_free(cfg);
    assert(!fclose(output));
    return 0;
}
