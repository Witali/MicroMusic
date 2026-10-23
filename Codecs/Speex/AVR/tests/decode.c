/* Host oracle: the original fixed-point API, enhancement and highpass off. */
#include <stdio.h>
#include <stdint.h>
#include "speex/speex.h"
#include "speex/speex_bits.h"
#ifdef SPEEX_AVR_PROFILE
#include "speex_avr.h"
#endif

int main(int argc, char **argv)
{
    unsigned char packet[20];
    spx_int16_t pcm[160];
    spx_int32_t off = 0;
    size_t n;
    unsigned frames = 0;
    FILE *input, *output;
    void *state;
    SpeexBits bits;
    if (argc != 3) return 2;
    input = fopen(argv[1], "rb");
    output = fopen(argv[2], "wb");
    if (!input || !output) return 3;
#ifdef SPEEX_AVR_PROFILE
    speex_avr_init();
#else
    state = speex_decoder_init(&speex_nb_mode);
    if (!state) return 4;
    speex_decoder_ctl(state, SPEEX_SET_ENH, &off);
    speex_decoder_ctl(state, SPEEX_SET_HIGHPASS, &off);
    speex_bits_init_buffer(&bits, packet, sizeof(packet));
#endif
    while ((n = fread(packet, 1, sizeof(packet), input)) != 0) {
        if (n != 20 || (packet[0] >> 3) != 3) return 5;
#ifdef SPEEX_AVR_PROFILE
        if (speex_avr_decode(packet, sizeof(packet), pcm) != 0) return 6;
#else
        speex_bits_set_bit_buffer(&bits, packet, sizeof(packet));
        if (speex_decode_int(state, &bits, pcm) != 0 || bits.overflow) return 6;
#endif
        /* Explicit s16le output also works on big-endian hosts. */
        for (n = 0; n < 160; ++n) {
            if (fputc((uint16_t)pcm[n] & 255, output) == EOF ||
                fputc((uint16_t)pcm[n] >> 8, output) == EOF) return 7;
        }
        ++frames;
    }
    if (ferror(input) || fclose(output)) return 8;
    fclose(input);
#ifdef SPEEX_AVR_PROFILE
    printf("static state+scratch=%zu scratch_peak=%zu\n", speex_avr_state_bytes(), speex_avr_scratch_peak());
#else
    speex_bits_destroy(&bits);
    speex_decoder_destroy(state);
#endif
    printf("%u frames\n", frames);
    return 0;
}
