#ifndef MICROMUSIC_ATTINY13A_SWITCHED_CLOCK_H
#define MICROMUSIC_ATTINY13A_SWITCHED_CLOCK_H
#include <stdint.h>

#define AT13_SWITCHED_CLOCK_PS_PER_SECOND UINT64_C(1000000000000)
#define AT13_SWITCHED_CLOCK_NEVER UINT64_MAX
enum { AT13_SWITCHED_CLOCK_OK=1, AT13_SWITCHED_CLOCK_BAD_ARGUMENT=-1,
 AT13_SWITCHED_CLOCK_BAD_TIME=-2, AT13_SWITCHED_CLOCK_OVERFLOW=-3 };
typedef struct {
 uint64_t time_ps, source_half, phase;
 uint32_t frequency_hz;
 uint8_t enabled, initialized;
} attiny13a_switched_clock_t;

/* Constant-frequency logical fixture, initial abstract output high. Public
 * fields are read-only; output = !(source_half&1). Frequency1..20,000,000Hz,
 * enabled exactly0/1, timestamps<MAX. No runtime frequency-change API.
 * Init: source_half0/phase0. All rejected operations leave state unchanged. */
int attiny13a_switched_clock_init(attiny13a_switched_clock_t *s,
 uint64_t time_ps,uint32_t frequency_hz,int enabled);

/* O(1) exact elapsed-time mapping, no queue or per-source-edge iteration.
 * Enabled: floor((delta*2*Hz+phase)/1e12) source halves, retaining remainder.
 * Disabled: advance wall time only, freezing source_half/phase/output. */
int attiny13a_switched_clock_advance(attiny13a_switched_clock_t *s,uint64_t to_ps);

/* Applies at s->time_ps. Preserve source_half and phase, emitting no edge.
 * Repeating the current enabled value is harmless. */
int attiny13a_switched_clock_set_enabled(attiny13a_switched_clock_t *s,int enabled);

/* Exact earliest absolute ps reaching requested RELATIVE source halves:
 * now+ceil((requested*1e12-phase)/(2*Hz)). Zero=>now even if disabled.
 * Disabled/nonzero, invalid state, overflow or reserved MAX endpoint=>NEVER.
 * Read-only; the caller merges this deadline with its other domains. */
uint64_t attiny13a_switched_clock_deadline_halves(const attiny13a_switched_clock_t *s,
 uint64_t requested);
#endif
