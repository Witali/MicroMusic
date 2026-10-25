// Complete, standalone profiling firmware. Frozen decoder remains in src/.
// Registers and interrupt vectors come from the installed AVR-LibC headers.
// Test output: OC2B (PD3); PB0 toggles after every Timer1 output tick.
#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/atomic.h>
#include <stdint.h>
#include "Lpx4HybridCore.h"
#include "voice_data.h"

static Lpx4HybridCore decoder;
static uint8_t queue[512];
static volatile uint16_t head, tail;
extern "C" {
volatile uint8_t profile_ready, profile_running, profile_done, profile_error;
volatile uint8_t profile_decode_active, profile_output_valid, profile_producer_done;
volatile uint32_t profile_produced, profile_played, profile_underruns;
volatile uint16_t profile_min_occupancy = 511;
volatile uint16_t profile_occupancy;
volatile const uint16_t profile_pwm_address = _SFR_MEM_ADDR(OCR2B);
volatile const uint16_t profile_spl_address = _SFR_MEM_ADDR(SPL);
volatile const uint16_t profile_sph_address = _SFR_MEM_ADDR(SPH);
}

ISR(TIMER1_COMPA_vect) {
    const uint16_t available = (head - tail) & 511;
    profile_occupancy = available;
    if (!profile_producer_done && available < profile_min_occupancy)
        profile_min_occupancy = available;
    uint8_t sample = 128;
    profile_output_valid = available != 0;
    if (available) {
        sample = queue[tail];
        tail = (tail + 1) & 511;
        ++profile_played;
    } else {
        ++profile_underruns;
    }
    OCR2B = sample;
    PINB = _BV(PINB0); // C hardware access; one observable edge per output tick.
    if (profile_producer_done && head == tail) {
        TCCR1B = 0;
        TIMSK1 = 0;
        profile_running = 0;
        profile_done = 1;
    }
}

static bool produce() {
    uint8_t value;
    profile_decode_active = 1;
    const bool ok = decoder.next(value);
    if (ok) ++profile_produced;
    profile_decode_active = 0;
    if (!ok) {
        profile_error = 1;
        return false;
    }
    const uint16_t next = (head + 1) & 511;
    queue[head] = value;
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { head = next; }
    return true;
}

int main() {
    if (!decoder.begin(profile_voice, sizeof(profile_voice))) {
        profile_error = profile_done = 1;
        for (;;) {}
    }
    profile_ready = 1;
    const uint32_t total = decoder.samples();
    const uint16_t prefill = total < 384 ? (uint16_t)total : 384;
    while (profile_produced < prefill) if (!produce()) break;
    if (profile_error) {
        profile_done = 1;
        for (;;) {}
    }
    DDRD |= _BV(DDD3);
    DDRB |= _BV(DDB0);
    TCCR2A = _BV(COM2B1) | _BV(WGM21) | _BV(WGM20);
    TCCR2B = _BV(CS20);
    OCR2B = 128;
    TCCR1A = TCCR1B = 0;
    TCNT1 = 0;
    OCR1A = 1999; // 16 MHz / 8000 Hz - 1.
    TIFR1 = _BV(OCF1A);
    TIMSK1 = _BV(OCIE1A);
    profile_running = 1;
    TCCR1B = _BV(WGM12) | _BV(CS10);
    sei();
    while (profile_produced < total && !profile_error) {
        uint16_t consumer;
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { consumer = tail; }
        if (((head + 1) & 511) != consumer) produce();
    }
    profile_producer_done = 1;
    if (!decoder.finished()) profile_error = 1;
    while (!profile_done) {}
    cli();
    for (;;) {}
}
