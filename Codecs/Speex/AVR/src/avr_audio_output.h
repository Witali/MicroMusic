/* ATmega328P/328, 16 MHz. Hardware routing is independent of decoder arithmetic.
 * Manufacturer register/vector definitions come from avr/io.h.
 * SPEEX_AVR_PWM_PIN=3: OC2B PWM + Timer1 PCM; =9: OC1A PWM + Timer2 PCM.
 * Existing low-level player builds retain D9; the Nano gallery selects D3. */
#ifndef MICROMUSIC_SPEEX_AVR_AUDIO_OUTPUT_H
#define MICROMUSIC_SPEEX_AVR_AUDIO_OUTPUT_H
#include <avr/io.h>
#if !defined(__AVR_ATmega328P__) && !defined(__AVR_ATmega328__)
#error This audio player requires ATmega328P or ATmega328
#endif
#ifndef F_CPU
#define F_CPU 16000000UL
#endif
#if F_CPU != 16000000UL
#error These audio timing profiles require 16 MHz
#endif
#ifndef SPEEX_AVR_PWM_PIN
#define SPEEX_AVR_PWM_PIN 9
#endif
#if SPEEX_AVR_PWM_PIN != 3 && SPEEX_AVR_PWM_PIN != 9
#error SPEEX_AVR_PWM_PIN must be 3 or 9
#endif
#if SPEEX_AUDIO_SAMPLE_HZ != 8000 && SPEEX_AUDIO_SAMPLE_HZ != 16000
#error Select an 8 or 16 kHz audio profile
#endif

#if SPEEX_AVR_PWM_PIN == 3
#define SPEEX_AUDIO_PWM OCR2B
#define SPEEX_AUDIO_PCM_VECTOR TIMER1_COMPA_vect
#else
#define SPEEX_AUDIO_PWM OCR1A
#define SPEEX_AUDIO_PCM_VECTOR TIMER2_COMPA_vect
#endif

static inline __attribute__((always_inline)) void speex_audio_init(void)
{
#if SPEEX_AVR_PWM_PIN == 3
    DDRD |= (1 << PD3);
    OCR2B = 128;
    TCCR2A = (1 << COM2B1) | (1 << WGM21) | (1 << WGM20);
    TCCR2B = (1 << CS20);
    TCCR1A = 0;
    TCCR1B = (1 << WGM12);
    OCR1A = F_CPU / SPEEX_AUDIO_SAMPLE_HZ - 1;
#else
    DDRB |= (1 << PB1);
    OCR1A = 128;
    TCCR1A = (1 << COM1A1) | (1 << WGM10);
    TCCR1B = (1 << WGM12) | (1 << CS10);
    TCCR2A = (1 << WGM21);
    OCR2A = F_CPU / 8 / SPEEX_AUDIO_SAMPLE_HZ - 1;
#endif
}
static inline __attribute__((always_inline)) void speex_audio_start(void)
{
#if SPEEX_AVR_PWM_PIN == 3
    TCNT1 = 0;
    TIFR1 = (1 << OCF1A);
    TIMSK1 = (1 << OCIE1A);
    TCCR1B = (1 << WGM12) | (1 << CS10);
#else
    TCNT2 = 0;
    TIFR2 = (1 << OCF2A);
    TIMSK2 = (1 << OCIE2A);
    TCCR2B = (1 << CS21);
#endif
}
static inline __attribute__((always_inline)) void speex_audio_stop(void)
{
#if SPEEX_AVR_PWM_PIN == 3
    TCCR1B = (1 << WGM12);
    TIMSK1 = 0;
#else
    TCCR2B = 0;
    TIMSK2 = 0;
#endif
}
#endif
