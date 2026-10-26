/* Host oracle: the original fixed-point API, enhancement and highpass off. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "speex/speex.h"
#include "speex/speex_bits.h"
#ifdef SPEEX_AVR_PROFILE
#include "speex_nb3.h"
#include <string.h>
#include <assert.h>
#endif

int main(int argc, char **argv)
{
    unsigned char packet[28];
    size_t packet_bytes=argc==4?(size_t)atoi(argv[3]):20;
    spx_int16_t pcm[160];
    spx_int32_t off = 0;
    size_t n;
    unsigned frames = 0;
    FILE *input, *output;
    void *state;
    SpeexBits bits;
    if ((argc != 3 && argc != 4) || (packet_bytes!=20 && packet_bytes!=28)) return 2;
    input = fopen(argv[1], "rb");
    output = fopen(argv[2], "wb");
    if (!input || !output) return 3;
#ifdef SPEEX_AVR_PROFILE
    speex_nb3_init();
#else
    state = speex_decoder_init(&speex_nb_mode);
    if (!state) return 4;
    speex_decoder_ctl(state, SPEEX_SET_ENH, &off);
    speex_decoder_ctl(state, SPEEX_SET_HIGHPASS, &off);
    speex_bits_init_buffer(&bits, packet, sizeof(packet));
#endif
    while ((n = fread(packet, 1, packet_bytes, input)) != 0) {
        if (n != packet_bytes || (packet[0] >> 3) != (packet_bytes==20?3:4)) return 5;
#ifdef SPEEX_AVR_PROFILE
        {
            unsigned char invalid[28];
            memset(pcm, 0x5a, sizeof(pcm));
            memcpy(invalid, packet, packet_bytes);
            invalid[0] = 0x80; /* WB header */
            assert(speex_nb3_decode(invalid, packet_bytes, pcm) == -1);
            invalid[0] = 0x10; /* NB mode 2 */
            assert(speex_nb3_decode(invalid, packet_bytes, pcm) == -1);
            assert(speex_nb3_decode(packet, packet_bytes-1, pcm) == -1);
            assert(speex_nb3_decode(packet, packet_bytes+1, pcm) == -1);
            assert(speex_nb3_decode(NULL, packet_bytes, pcm) == -1);
            assert(speex_nb3_decode(packet, packet_bytes, NULL) == -1);
            for (n = 0; n < 160; ++n) assert(pcm[n] == 0x5a5a);
        }
        if (speex_nb3_decode(packet, packet_bytes, pcm) != 0) return 6;
#else
        speex_bits_set_bit_buffer(&bits, packet, packet_bytes);
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
    printf("static state+scratch=%zu scratch_peak=%zu\n", speex_nb3_state_bytes(), speex_nb3_scratch_peak());
#else
    speex_bits_destroy(&bits);
    speex_decoder_destroy(state);
#endif
    printf("%u frames\n", frames);
    return 0;
}
