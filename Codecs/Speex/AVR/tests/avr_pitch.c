/* Mailbox for exact NB3 signed8-gain pitch products and accumulation. */
#include <stdint.h>
extern void speex_avr_pitch_add(int32_t *,const int16_t *,int16_t,uint8_t,uint8_t);
volatile uint8_t pitch_status,pitch_command,pitch_count,pitch_accumulate,pitch_zero;
volatile int16_t pitch_gain;
int16_t pitch_input[40];
int32_t pitch_output[40];
int main(void)
{
    pitch_status=1;
    for (;;) if (pitch_command) {
        pitch_command=0;
        speex_avr_pitch_add(pitch_output,pitch_input,pitch_gain,pitch_count,pitch_accumulate);
        __asm__ volatile("mov %0,r1" : "=r"(pitch_zero));
        pitch_status=2;
    }
}
