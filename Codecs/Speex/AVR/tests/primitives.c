#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "lsp.h"
#include "speex/speex_bits.h"

void reference_lsp(const spx_lsp_t *, spx_coef_t *, int, char *);
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
        reference_lsp(angles, a, 10, arena.bytes);
        lsp_to_lpc(angles, b, 10, arena.bytes);
        assert(memcmp(a, b, sizeof(a)) == 0);
    }
    puts("PASS: 3670016 bit fields and 240000 complete upstream LSP conversions");
    return 0;
}
