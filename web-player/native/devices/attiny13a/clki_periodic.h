#ifndef MICROMUSIC_ATTINY13A_CLKI_PERIODIC_H
#define MICROMUSIC_ATTINY13A_CLKI_PERIODIC_H
#include "clki_input.h"

/* Compact FINITE description of an exact logical edge stream. No allocator,
 * inferred frequency, queue ownership, pad/divider or CPU effects. All fields
 * are read-only to callers. MAX is reserved for absent next_time, not a time. */
enum { AT13_CLKI_PERIODIC_OK=1, AT13_CLKI_PERIODIC_EMPTY=0,
 AT13_CLKI_PERIODIC_BAD_ARGUMENT=-1, AT13_CLKI_PERIODIC_BAD_TIME=-2 };
typedef struct {
 uint64_t next_time_ps, high_ps, low_ps, remaining_edges, horizon_ps;
 uint8_t initial_level, current_level, next_level, initialized;
} attiny13a_clki_periodic_t;

/* Explicit positive durations, count and inclusive horizon. Count0 describes
 * a known hold with no edge. No timestamp may equal MAX. Validate the entire
 * finite tail before mutation; overflow/horizon errors leave state unchanged.
 * Final time = start + floor(count/2)*high + floor(count/2)*low +
 *             (odd count ? (initial_level ? high : low) :0).
 * Unused durations need not fit a fictitious edge beyond the finite count. */
int attiny13a_clki_periodic_init(attiny13a_clki_periodic_t *s,
 uint64_t start_ps,uint8_t initial_level,uint64_t high_ps,uint64_t low_ps,
 uint64_t edge_count,uint64_t known_until_ps);

/* Peek writes only on OK, with no producer mutation. Output must be non-NULL
 * and disjoint from state. EMPTY/error leaves output unchanged. Consume moves
 * current_level to the peeked level and computes only the next ACTUAL edge;
 * EMPTY/error changes nothing. Once exhausted, next_time=MAX and the declared
 * horizon remains a hold, never an invitation to extrapolate another edge. */
int attiny13a_clki_periodic_peek(const attiny13a_clki_periodic_t *s,
 attiny13a_clki_edge_t *edge);
int attiny13a_clki_periodic_consume(attiny13a_clki_periodic_t *s);
#endif
