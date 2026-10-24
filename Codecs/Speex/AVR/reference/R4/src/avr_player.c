/*
 * ATmega328P 16 MHz player for 8-kbit/s Speex NB mode 3 frames in program FLASH.
 * OC1A / PB1 / Arduino D9 -> RC low-pass -> audio amplifier (not speaker directly).
 * Timer1 PWM = 16 MHz / 256 = 62.5 kHz. Timer2 interrupt = 8000 Hz.
 * Input is a RAW sequence of 20-byte Speex frames, not .spx Ogg data.
 * IMPORTANT: Experimental; verify timing before deploying.
 */
#ifndef F_CPU
#define F_CPU 16000000UL
#endif
#include <avr/io.h>
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include "speex_nb8.h"
#include "sample_data.h"

#if F_CPU != 16000000UL
#error "This Timer2 setup assumes F_CPU=16 MHz"
#endif

#define AUDIO_FRAME 160
static SpeexNB8 decoder;
static uint8_t packet[NB8_BYTES];
static int16_t scratch[AUDIO_FRAME];
static volatile uint8_t playback[2][AUDIO_FRAME];
static volatile uint8_t ready[2];
static volatile uint8_t read_bank;
static volatile uint8_t read_pos;
static volatile uint16_t underflows;

/* At 8kHz sampling Timer2 CTC interrupt runs every 125us */
ISR(TIMER2_COMPA_vect) {
    uint8_t bank = read_bank;
    if (ready[bank]) {
        OCR1A = playback[bank][read_pos];
        if (++read_pos == AUDIO_FRAME) {
            ready[bank]=0;
            read_pos=0;
            read_bank=bank^1;
        }
    } else {
        OCR1A = 128; /* silence, center of 8-bit PWM range */
        ++underflows;
    }
}

static void setup_audio(void) {
    DDRB |= _BV(DDB1);
    /* Fast PWM 8bit, non-inverting OC1A, clk/1, 62.5kHz carrier */
    TCCR1A = _BV(COM1A1) | _BV(WGM10);
    TCCR1B = _BV(WGM12) | _BV(CS10);
    OCR1A=128;
    /* Timer2 CTC f=16MHz/(8*(249+1))=8,000 Hz */
    TCCR2A = _BV(WGM21);
    TCCR2B = _BV(CS21);
    OCR2A=249;
    TCNT2=0;
    TIMSK2 = _BV(OCIE2A);
    sei();
}

int main(void) {
    speex_nb8_init(&decoder);
    setup_audio();
    for (;;) {
        for (uint16_t frame=0;frame<SAMPLE_FRAME_COUNT;frame++) {
            /* Alternating buffers. Wait for the one we need to become free. */
            uint8_t bank=(uint8_t)(frame&1u);
            while (ready[bank]) { /* PCM interrupt keeps running */ }
            uint16_t offset = (uint16_t)frame * NB8_BYTES;
            for(uint8_t i=0;i<NB8_BYTES;i++) {
                packet[i]=pgm_read_byte(&sample_spxraw[offset+i]);
            }
            if (speex_nb8_decode(&decoder,packet,scratch)!=0) {
                for(uint8_t i=0;i<AUDIO_FRAME;i++) playback[bank][i]=128;
            } else {
                for(uint8_t i=0;i<AUDIO_FRAME;i++) {
                    int16_t s=scratch[i];
                    /* Clip signed 16-bit PCM -> unsigned 8bit PWM */
                    int16_t u=(int16_t)(s>>8)+128;
                    if (u<0) u=0;
                    if (u>255) u=255;
                    playback[bank][i]=(uint8_t)u;
                }
            }
            __asm__ __volatile__("" ::: "memory"); /* publish buffer before ready */
            ready[bank]=1;
        }
        /* Replay from the beginning without reusing old decoder histories. */
        while (ready[0]||ready[1]) { }
        /* Synchronize producer and ISR when restarting, including odd frame counts. */
        cli();
        read_bank = 0;
        read_pos = 0;
        OCR1A = 128;
        sei();
        speex_nb8_init(&decoder);
    }
}
