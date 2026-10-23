#ifndef MICROMUSIC_ATTINY13A_CLKI_INPUT_H
#define MICROMUSIC_ATTINY13A_CLKI_INPUT_H
#include <stdint.h>

/* Logical CLKI input for the ATtiny13A board owner. Absolute uint64 ps; MAX is
 * reserved, never a timestamp. This queue has no allocator, callbacks, clock
 * extrapolation, pad resolution, divider or CPU ownership. Electrical timing,
 * source/internal phase and waveform qualification remain separate work. */
#define AT13_CLKI_NEVER UINT64_MAX
enum {
 AT13_CLKI_OK=1, AT13_CLKI_EMPTY=0,
 AT13_CLKI_BACKPRESSURE=-1, AT13_CLKI_BAD_ARGUMENT=-2,
 AT13_CLKI_BAD_TIME=-3, AT13_CLKI_BAD_LEVEL=-4,
 AT13_CLKI_UNKNOWN_HORIZON=-5, AT13_CLKI_EDGE_PENDING=-6
};
typedef struct {
 uint64_t time_ps;
 uint8_t level;
} attiny13a_clki_edge_t;
typedef struct {
 attiny13a_clki_edge_t *storage;
 uint64_t now_ps, known_until_ps;
 uint32_t capacity, head, count;
 uint8_t level;
} attiny13a_clki_input_t;

/* Caller owns a disjoint state object and capacity-element storage for their
 * entire lifetime. Init starts at the explicit level with horizon=initial_ps;
 * it neither initializes storage bytes nor invents a transition. All failed
 * operations (including init) leave state, storage and output unchanged. */
int attiny13a_clki_init(attiny13a_clki_input_t *q,
 attiny13a_clki_edge_t *storage, uint32_t capacity,
 uint64_t initial_ps, uint8_t initial_level);

/* Atomically validate/copy a batch AND publish its inclusive known horizon.
 * Every new time must be strictly after the OLD published horizon and previous
 * tail time, at/before known_until_ps, and below MAX. Levels must alternate
 * from the queued tail (or current level when empty). Horizon is nondecreasing.
 * No partial acceptance on malformed input or insufficient free capacity.
 * count=0, edges=NULL publishes an edge-free hold; an equal horizon is valid.
 * Source array must not overlap state or storage. Rejections are nonsticky.
 * No concurrent producer/consumer access: the board owner serializes calls. */
int attiny13a_clki_enqueue(attiny13a_clki_input_t *q,
 const attiny13a_clki_edge_t *edges, uint32_t count, uint64_t known_until_ps);

/* Peek is nondestructive. Consume advances now/level to the next queued edge;
 * the owner merges that timestamp with all other domains before consuming it.
 * Empty returns EMPTY and does not mutate output. Peek requires output;
 * consume permits NULL to discard an already-peeked edge. Non-NULL output
 * must not overlap state/storage. Neither call fabricates an unqueued edge. */
int attiny13a_clki_peek(const attiny13a_clki_input_t *q, attiny13a_clki_edge_t *edge);
int attiny13a_clki_consume(attiny13a_clki_input_t *q, attiny13a_clki_edge_t *edge);

/* Advance an edge-free interval only. UNKNOWN_HORIZON means the producer has
 * not described that far; EDGE_PENDING means an actual edge at/before at_ps
 * must be consumed first. Equality with a pending edge is not a hold. A known
 * high/low hold is valid progress in wall time, never a generated clock pulse. */
int attiny13a_clki_hold_until(attiny13a_clki_input_t *q, uint64_t at_ps);

/* For NULL/zero-initialized state: times return NEVER, level returns255, counts0.
 * Otherwise getters have no side effects. Callers must not edit state fields. */
uint64_t attiny13a_clki_now(const attiny13a_clki_input_t *q);
uint64_t attiny13a_clki_horizon(const attiny13a_clki_input_t *q);
uint8_t attiny13a_clki_level(const attiny13a_clki_input_t *q);
uint32_t attiny13a_clki_count(const attiny13a_clki_input_t *q);
uint32_t attiny13a_clki_free(const attiny13a_clki_input_t *q);
#endif
