/* Independent native KISS reference plus exact integer-C outputs for AVR replay. */
#include "fixed_inverse.h"
#include "kiss_fftr.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint32_t seed = 1;
static float next(void) {
    seed = seed * UINT32_C(1664525) + UINT32_C(1013904223);
    return ((int32_t)(seed >> 8) - 8388608) / 8388608.0f;
}
static void write_float(FILE *f, float value) {
    uint32_t bits; memcpy(&bits, &value, 4);
    for (unsigned i=0; i<4; ++i) assert(fputc((bits >> (8*i)) & 255, f) != EOF);
}
int main(int argc, char **argv) {
    assert(argc == 4 && sizeof(float) == 4);
    FILE *inputs=fopen(argv[1],"wb"), *integers=fopen(argv[2],"wb"), *reference=fopen(argv[3],"wb");
    assert(inputs && integers && reference);
    kiss_fftr_cfg inverse=kiss_fftr_alloc(512,1,NULL,NULL); assert(inverse);
    for (unsigned trial=0; trial<512; ++trial) {
        compact_transform fixed; kiss_fft_cpx input[257]; float original[512];
        float scale=ldexpf(1.0f,(int)(trial%33)-16);
        for (unsigned k=0; k<=256; ++k) {
            float r=trial==0 ? 0 : trial<=257 ? (float)(k==trial-1) : next();
            float im=trial<=257 ? 0 : next();
            input[k].r=fixed.frequency[k].r=r*scale; input[k].i=fixed.frequency[k].i=im*scale;
            write_float(inputs,r*scale); write_float(inputs,im*scale);
        }
        kiss_fftri(inverse,input,original); codec2_fixed_inverse(&fixed);
        for (unsigned i=0; i<512; ++i) { write_float(integers,fixed.time[i]); write_float(reference,original[i]); }
    }
    kiss_fftr_free(inverse);
    assert(!fclose(inputs) && !fclose(integers) && !fclose(reference));
    return 0;
}
