#include "codec2_decoder.h"
#include <stdint.h>

static codec2_decoder decoder;
volatile uint8_t codec2_decode_status;
volatile uint8_t codec2_decode_command;
volatile int8_t codec2_decode_result;
uint8_t codec2_decode_packet[8];
int16_t codec2_decode_pcm[160];
volatile uint16_t codec2_decode_state_bytes;
volatile uint16_t codec2_decode_fft_bytes;

int main(void) {
    codec2_decode_state_bytes = sizeof(decoder);
    codec2_decode_result = codec2_decoder_init(&decoder);
    codec2_decode_fft_bytes = decoder.fft_bytes;
    codec2_decode_status = codec2_decode_result ? 0xe0 : 1;
    for (;;) {
        if (codec2_decode_command) {
            uint8_t command = codec2_decode_command;
            codec2_decode_command = 0;
            codec2_decode_result = command == 2 ? codec2_decoder_init(&decoder)
                : codec2_decoder_decode(&decoder, codec2_decode_packet, 8, codec2_decode_pcm);
            codec2_decode_status = codec2_decode_result ? 3 : 2;
            __asm__ __volatile__("" ::: "memory");
        }
    }
}
