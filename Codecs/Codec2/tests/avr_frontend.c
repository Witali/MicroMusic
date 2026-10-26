/* Byte mailbox for independent execution of the linked C on actual AVR ISA. */
#include "codec2_3200.h"
volatile uint8_t codec2_test_status;
volatile uint8_t codec2_test_command;
uint8_t codec2_test_packet[8];
codec2_3200_params codec2_test_params;

int main(void) {
    codec2_test_status = 1;
    for (;;) {
        if (codec2_test_command) {
            codec2_test_command = 0;
            codec2_test_status = codec2_3200_unpack(codec2_test_packet, 8, &codec2_test_params) ? 3 : 2;
            __asm__ __volatile__("" ::: "memory");
        }
    }
}
