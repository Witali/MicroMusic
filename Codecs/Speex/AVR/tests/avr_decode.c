/* SRAM mailbox for ISA validation, not the PWM player. No heap or serial I/O.
 * command: 1 decode packet, 2 reset; status: 1 ready, 2 complete. */
#include "speex_avr.h"
#include <avr/io.h>

#ifndef SPEEX_TEST_PACKET_BYTES
#define SPEEX_TEST_PACKET_BYTES 20
#endif
uint8_t speex_test_packet[SPEEX_TEST_PACKET_BYTES];
int16_t speex_test_pcm[160];
volatile uint8_t speex_test_command;
volatile uint8_t speex_test_status;
volatile int8_t speex_test_result;

int main(void)
{
    speex_avr_init();
    speex_test_status = 1;
    for (;;) {
        if (speex_test_command == 1) {
            speex_test_result = speex_avr_decode(speex_test_packet, SPEEX_TEST_PACKET_BYTES, speex_test_pcm);
            speex_test_command = 0;
            speex_test_status = 2;
        } else if (speex_test_command == 2) {
            speex_avr_init();
            speex_test_command = 0;
            speex_test_status = 1;
        }
    }
}
