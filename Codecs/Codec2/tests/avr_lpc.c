#include "codec2_lpc.h"
volatile uint8_t codec2_lpc_test_status;
volatile uint8_t codec2_lpc_test_command;
uint16_t codec2_lpc_test_lsp[10];
int32_t codec2_lpc_test_ak[11];

int main(void) {
    codec2_lpc_test_status = 1;
    for (;;) {
        if (codec2_lpc_test_command) {
            codec2_lpc_test_command = 0;
            codec2_lsp_to_lpc_q23(codec2_lpc_test_lsp, codec2_lpc_test_ak);
            codec2_lpc_test_status = 2;
            __asm__ __volatile__("" ::: "memory");
        }
    }
}
