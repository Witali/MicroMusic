/* ATmega328P @ 16 MHz: 62.5 kHz 8-bit PWM on OC1A / PB1 / Arduino D9.
 * Timer2 CTC advances PCM at 8 kHz. Emit each decoded 40-sample subframe
 * through a 128-byte ring; two complete s16 PCM frames would exceed SRAM. */
#include "speex_avr.h"
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include "sample.h"

static volatile uint8_t ring[128];
static volatile uint8_t head, tail, input_finished;
volatile uint8_t speex_player_started;
volatile uint8_t speex_player_done;
volatile uint8_t speex_player_error;
volatile uint16_t speex_player_underruns;
static int16_t pcm[160];
static uint8_t packet[20];

/* Test-only admission load: reserve this much CPU work in every audio frame.
 * Interrupts remain enabled during steady playback. Empty assembly labels
 * let the ISA verifier count the exact injected instruction cycles, excluding
 * ISR cycles. No function or instructions are emitted in the ordinary build. */
#if defined(SPEEX_AVR_FRAME_LOAD_CYCLES) && SPEEX_AVR_FRAME_LOAD_CYCLES > 0
static __attribute__((noinline,noclone)) void speex_player_frame_load(void)
{
    __asm__ volatile (".global speex_player_load_begin\nspeex_player_load_begin:");
    __builtin_avr_delay_cycles(SPEEX_AVR_FRAME_LOAD_CYCLES);
    __asm__ volatile (".global speex_player_load_end\nspeex_player_load_end:");
}
#endif

ISR(TIMER2_COMPA_vect)
{
    if (tail != head) {
        OCR1A = ring[tail];
        tail = (tail + 1) & 127;
    } else {
        OCR1A = 128;
        if (input_finished) {
            TCCR2B = 0;
            TIMSK2 = 0;
            speex_player_done = 1;
        } else {
            ++speex_player_underruns;
        }
    }
}

void speex_avr_output(const int16_t *samples, uint8_t count)
{
    uint8_t write, i;
    while (((tail - head - 1) & 127) < count) { }
    write = head;
    for (i = 0; i < count; ++i) {
        ring[write] = ((uint16_t)samples[i] >> 8) ^ 128;
        write = (write + 1) & 127;
    }
    head = write;
    if (!speex_player_started && head >= 80) {
        speex_player_started = 1;
        TCNT2 = 0;
        TIFR2 = (1 << OCF2A);
        TIMSK2 = (1 << OCIE2A);
        TCCR2B = (1 << CS21); /* 16 MHz / 8 / 250 = 8 kHz */
        sei();
    }
}

int main(void)
{
    uint16_t frame;
    uint8_t i;
    cli();
    DDRB |= (1 << PB1);
    OCR1A = 128;
    TCCR1A = (1 << COM1A1) | (1 << WGM10);
    TCCR1B = (1 << WGM12) | (1 << CS10);
    TCCR2A = (1 << WGM21);
    OCR2A = 249;
    speex_avr_init();
    for (frame = 0; frame < SPEEX_SAMPLE_FRAMES; ++frame) {
#if defined(SPEEX_AVR_FRAME_LOAD_CYCLES) && SPEEX_AVR_FRAME_LOAD_CYCLES > 0
        speex_player_frame_load();
#endif
        for (i = 0; i < 20; ++i)
            packet[i] = pgm_read_byte(sample_data + (uint16_t)(frame*20) + i);
        if (speex_avr_decode(packet, 20, pcm)) {
            speex_player_error = 1;
            break;
        }
    }
    input_finished = 1;
    while (!speex_player_done) { }
    for (;;) { }
}
