#ifndef MICROMUSIC_ATTINY13A_CLKI_CLOCK_H
#define MICROMUSIC_ATTINY13A_CLKI_CLOCK_H
#include <stdint.h>

/* Explicit digital fixture, not a silicon phase measurement. The board owns
 * timestamps, the CLKI queue/PB3 pad, total source-edge counts, domain gates and
 * CPU delivery. This module owns only the waveform/divider phase below. */
enum {
 AT13_CLKI_CLOCK_OK=1, AT13_CLKI_CLOCK_TRANSITION=1,
 AT13_CLKI_CLOCK_NONE=0, AT13_CLKI_CLOCK_BAD_ARGUMENT=-1
};
typedef struct {
 uint16_t divisor, pending_divisor, source_counter;
 uint8_t input_level, output_level, pending_wait_old_rise;
} attiny13a_clki_clock_t;

/* Public fields are read-only to callers. Divisors are powers of two1..256.
 * Init: D1 output=input; D>1 output0, counter0. It emits no transition.
 * All invalid calls leave the entire state and output argument unchanged. */
int attiny13a_clki_clock_init(attiny13a_clki_clock_t *s,
 uint8_t initial_level,uint32_t divisor);

/* Feed an ACTUAL alternating source transition, with running exactly0 or1.
 * running0 changes input_level only, freezing output/counter/pending request.
 * D1 follows new input transitions except those already matching output.
 * D>1 toggles output every D/2 active source RISING edges. source_counter is
 * this bounded phase residue, never an absolute source-edge count.
 * Return1 only for an actual output transition and write its new level to
 * *output_level. Return0 leaves *output_level unchanged; state may advance.
 * Output must be non-NULL and disjoint from s. No timestamps/extrapolation. */
int attiny13a_clki_clock_edge(attiny13a_clki_clock_t *s,
 uint8_t new_level,int running,uint8_t *output_level);

/* Keep the old waveform until its NEXT actual SYSTEM RISING transition; then
 * install the new divisor with output still high and counter0. Last valid
 * request replaces pending; same/current D uses the same next-old-rise rule.
 * At a CPU retirement rising edge this is the explicit T1+T2 lower-bound
 * fixture; arbitrary debug requests use the named next-old-rise semantics.
 * Requesting/gating never emits an output transition by itself. */
int attiny13a_clki_clock_request_divisor(attiny13a_clki_clock_t *s,uint32_t divisor);

/* Reset only the divider configuration/phase: preserve input AND output,
 * counter0, clear pending. This never invents a reset/gating edge. With D1 and
 * input!=output, the next transition already equal to output is ignored until
 * an actual opposite level arrives. The board chooses when reset applies. */
int attiny13a_clki_clock_reset_divisor(attiny13a_clki_clock_t *s,uint32_t divisor);
#endif
