/* Host adapter for the untouched upstream fixed-point narrowband oracle.
 * Packet width is explicit; enhancement and highpass match the AVR profile. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "speex/speex.h"
#include "speex/speex_bits.h"

int main(int argc, char **argv)
{
    if (argc != 4) return 2;
    unsigned width = (unsigned)atoi(argv[1]);
    if (width != 6 && width != 10 && width != 15 && width != 20 && width != 28) return 2;
    FILE *input = fopen(argv[2], "rb"), *output = fopen(argv[3], "wb");
    if (!input || !output) return 3;
    void *decoder = speex_decoder_init(&speex_nb_mode);
    if (!decoder) return 4;
    spx_int32_t off = 0;
    speex_decoder_ctl(decoder, SPEEX_SET_ENH, &off);
    speex_decoder_ctl(decoder, SPEEX_SET_HIGHPASS, &off);
    unsigned char packet[28];
    spx_int16_t pcm[160];
    SpeexBits bits;
    speex_bits_init_buffer(&bits, packet, sizeof(packet));
    size_t count;
    while ((count = fread(packet, 1, width, input)) != 0) {
        if (count != width) return 5;
        speex_bits_set_bit_buffer(&bits, packet, width);
        if (speex_decode_int(decoder, &bits, pcm) || bits.overflow) return 6;
        for (unsigned i = 0; i < 160; ++i)
            if (fputc((uint16_t)pcm[i] & 255, output) == EOF ||
                fputc((uint16_t)pcm[i] >> 8, output) == EOF) return 7;
    }
    if (ferror(input) || fclose(output)) return 8;
    fclose(input);
    speex_bits_destroy(&bits);
    speex_decoder_destroy(decoder);
    return 0;
}
