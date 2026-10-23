#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "lsp.h"
#include "quant_lsp.h"
#include "speex/speex_bits.h"

void reference_lsp(const spx_lsp_t *, spx_coef_t *, int, char *);
void reference_interpolate(spx_lsp_t *, spx_lsp_t *, spx_lsp_t *, int, int, int, spx_word16_t);
static uint32_t seed = 0x31415926;
static uint32_t random32(void) { seed ^= seed<<13; seed ^= seed>>17; seed ^= seed<<5; return seed; }

int main(void)
{
    unsigned word, offset, n, bit, test;
    char bytes[20] = {0};
    SpeexBits bits;
    for (word = 0; word < 65536; ++word) {
        bytes[0] = word >> 8;
        bytes[1] = word;
        for (offset = 0; offset < 8; ++offset) for (n = 1; n <= 7; ++n) {
            unsigned expected = 0;
            memset(&bits, 0, sizeof(bits));
            bits.chars = bytes; bits.nbBits = 160; bits.bitPtr = offset;
            for (bit = offset; bit < offset+n; ++bit)
                expected = expected*2 + (((uint8_t)bytes[bit/8] >> (7-bit%8)) & 1);
            assert(speex_bits_unpack_unsigned(&bits, n) == expected);
            assert(bits.charPtr*8 + bits.bitPtr == (int)(offset+n));
        }
    }
    memset(&bits, 0, sizeof(bits));
    bits.chars = bytes; bits.nbBits = 160; bits.charPtr = 19; bits.bitPtr = 7;
    assert(speex_bits_unpack_unsigned(&bits, 2) == 0 && bits.overflow);
    for (test = 0; test < 240000; ++test) {
        int i, j;
        spx_lsp_t angles[10];
        spx_coef_t a[10], b[10];
        union { uint32_t alignment; char bytes[4096]; } arena;
        for (i = 0; i < 10; ++i) angles[i] = (spx_lsp_t)(random32() % 25737);
        if (test < 120000) for (i = 1; i < 10; ++i) {
            spx_lsp_t x = angles[i];
            for (j = i; j && angles[j-1] > x; --j) angles[j] = angles[j-1];
            angles[j] = x;
        }
        if (test<36) {
            static const spx_lsp_t edge[6]={0,16,8192,12868,25720,25736};
            /* Include extrema, mixed signs and zero cosine in both first
             * polynomial pairs. Unordered inputs also stress saturation. */
            for (i=0;i<10;i++) angles[i]=edge[(i&1)?test/6:test%6];
            angles[2]=edge[test/6];angles[3]=edge[test%6];
        }
        reference_lsp(angles, a, 10, arena.bytes);
        lsp_to_lpc(angles, b, 10, arena.bytes);
        assert(memcmp(a, b, sizeof(a)) == 0);
    }
    puts("PASS: 3670016 bit fields and 240000 complete upstream LSP conversions");
    /* Upstream rounds each interpolation product separately. Equal arbitrary
     * odd angles do NOT interpolate identically at all four steps. NB3 angles
     * are multiples of 16; exhaust every 6+6+6-bit code triple to prove the
     * frame-cache invariant using untouched upstream interpolation. */
    for (test=0;test<(1u<<18);test++) {
        spx_lsp_t angles[10], final[10], current[10], previous[10]={0};
        unsigned sub,i;
        bytes[0]=test>>10;bytes[1]=test>>2;bytes[2]=test<<6;
        memset(&bits,0,sizeof(bits));bits.chars=bytes;bits.nbBits=18;
        lsp_unquant_lbr(angles,10,&bits);
        for (i=0;i<10;i++) assert((angles[i]&15)==0);
        reference_interpolate(previous,angles,final,10,3,4,16);
        for (sub=0;sub<4;sub++) {
            reference_interpolate(angles,angles,current,10,sub,4,16);
            assert(memcmp(final,current,sizeof(final))==0);
        }
    }
    puts("PASS: all 262144 NB3 LSP code triples preserve exact repeated-frame interpolation");
    return 0;
}
