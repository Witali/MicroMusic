/* Mailbox for exact NB3 signed8-gain pitch products and accumulation. */
#include <stdint.h>
extern void speex_avr_pitch_add24(uint8_t *,const int16_t *,int8_t,uint8_t,uint8_t);
volatile uint8_t pitch_status,pitch_command,pitch_count,pitch_accumulate,pitch_zero;
volatile int8_t pitch_gain;
int16_t pitch_input[40];
uint8_t pitch_output[3*40+4]; /* four-byte canary after packed output */
int main(void)
{
    pitch_status=1;
    for (;;) if (pitch_command) {
        pitch_command=0;
        speex_avr_pitch_add24(pitch_output,pitch_input,pitch_gain,pitch_count,pitch_accumulate);
        __asm__ volatile("mov %0,r1" : "=r"(pitch_zero));
        pitch_status=2;
    }
}
