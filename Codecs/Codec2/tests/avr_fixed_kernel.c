#include "fixed_inverse.h"
#include <stdint.h>
compact_transform codec2_fft_buffer;
volatile uint8_t codec2_fft_command, codec2_fft_status;
int main(void) {
    codec2_fft_status=1;
    for (;;) if (codec2_fft_command) {
        codec2_fft_command=0;
#if CODEC2_BENCH_FLOAT
        compact_inverse(&codec2_fft_buffer);
#else
        codec2_fixed_inverse(&codec2_fft_buffer);
#endif
        codec2_fft_status=2;
        __asm__ __volatile__("" ::: "memory");
    }
}
