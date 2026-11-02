/* Hardware-only test: no decoder or audio source. */
#include <avr/interrupt.h>
#include "avr_audio_output.h"
volatile uint8_t probe_started, probe_done, probe_count;
ISR(SPEEX_AUDIO_PCM_VECTOR)
{
    SPEEX_AUDIO_PWM = 32 + (probe_count & 3) * 48;
    if (++probe_count == 32) {
        speex_audio_stop();
        probe_done = 1;
    }
}
int main(void)
{
    cli();
    speex_audio_init();
    probe_started = 1;
    speex_audio_start();
    sei();
    for (;;) { }
}
