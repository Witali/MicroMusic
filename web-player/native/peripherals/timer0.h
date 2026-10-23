/* ATtiny13A Timer/Counter0. Microchip DS40002307A, chapters 11 and 12. */
#ifndef MICROMUSIC_ATTINY13A_TIMER0_H
#define MICROMUSIC_ATTINY13A_TIMER0_H

#include <stddef.h>
#include <stdint.h>
#include "../attiny13a-registers.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
 TIMER0_PRR = AT13_IO_PRR, TIMER0_GTCCR = AT13_IO_GTCCR, TIMER0_OCR0B = AT13_IO_OCR0B,
 TIMER0_TCCR0A = AT13_IO_TCCR0A, TIMER0_TCNT0 = AT13_IO_TCNT0, TIMER0_TCCR0B = AT13_IO_TCCR0B,
 TIMER0_OCR0A = AT13_IO_OCR0A, TIMER0_TIFR0 = AT13_IO_TIFR0, TIMER0_TIMSK0 = AT13_IO_TIMSK0,
 TIMER0_TOV0 = AT13_MASK_TOV0, TIMER0_OCF0A = AT13_MASK_OCF0A, TIMER0_OCF0B = AT13_MASK_OCF0B,
 TIMER0_OC0A = AT13_MASK_PORTB0, TIMER0_OC0B = AT13_MASK_PORTB1
};
enum {
 TIMER0_OK = 0, TIMER0_TIME_REVERSED = 1, TIMER0_RESERVED_WGM = 2,
 TIMER0_RESERVED_COM0B = 3, TIMER0_UNKNOWN_REGISTER = 4,
 TIMER0_POWERED_DOWN = 5, TIMER0_ZERO_PHASE_TOP = 6
};

/* Snapshot of the OC latches and peripheral override mux, NOT DDR/output drive.
 * PB0/OC0A = bit 0, PB1/OC0B = bit 1. A GPIO owner combines this with DDRB.
 * Values are valid starting at cycle. Several changes at one cycle coalesce. */
typedef struct {
 uint64_t cycle;
 uint8_t levels, overrides;
 uint8_t reserved[6];
} timer0_event_t;

typedef struct {
 uint64_t cycle;
 uint64_t scheduled_events; /* Diagnostic: event boundaries, not CPU clocks. */
 uint16_t prescaler;       /* Free-running phase, independent of CS02:0. */
 uint8_t tccra, tccrb, tcnt, ocra, ocrb, active_a, active_b;
 uint8_t tifr, timsk, gtccr, prr;
 uint8_t descending, block_compare, fast_clear, clock_enabled;
 uint8_t levels, overrides;
 timer0_event_t *events;
 uint32_t capacity, head, count;
 uint64_t dropped_events; /* Nonzero means capture is incomplete; never hidden. */
} timer0_t;

/* Caller owns storage, which may be in WASM linear memory. NULL/0 explicitly
 * disables capture. No allocation, callbacks, host imports or JS calls. */
void timer0_init(timer0_t *timer, timer0_event_t *events, uint32_t capacity,
                 uint64_t cycle);
int timer0_advance(timer0_t *timer, uint64_t cycle);
int timer0_write(timer0_t *timer, uint64_t cycle, uint8_t io_address,
                uint8_t value);
int timer0_read(timer0_t *timer, uint64_t cycle, uint8_t io_address,
               uint8_t *value);
/* UINT64_MAX when no autonomous Timer0 event is scheduled. This includes
 * compare-flag, TOP/BOTTOM, prescaler-blocking and output transitions. */
uint64_t timer0_next_event(const timer0_t *timer);
uint8_t timer0_irq_pending(const timer0_t *timer);
void timer0_irq_ack(timer0_t *timer, uint8_t flag_mask);
/* clkI/O gating, e.g. ADC Noise Reduction/Power-down; Idle leaves it enabled. */
int timer0_set_clock_enabled(timer0_t *timer, uint64_t cycle, int enabled);
/* T0 edge AFTER GPIO synchronization and edge detection. Counts immediately
 * at this cycle if CS02:0 selects this edge and the module clock is enabled.
 * The GPIO owner models the documented 2.5-3.5 clkI/O asynchronous latency. */
int timer0_external_edge(timer0_t *timer, uint64_t cycle, int rising);
/* Read a contiguous batch without copying, then consume it in C/WASM or once
 * per host block. On overflow newest events are dropped, state remains exact,
 * and dropped_events increases. The caller must treat that as capture failure. */
const timer0_event_t *timer0_events(const timer0_t *timer, uint32_t *count);
void timer0_consume_events(timer0_t *timer, uint32_t count);
void timer0_clear_events(timer0_t *timer);

#ifdef __cplusplus
}
#endif
#endif
