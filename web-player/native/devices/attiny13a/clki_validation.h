#ifndef MICROMUSIC_ATTINY13A_CLKI_VALIDATION_H
#define MICROMUSIC_ATTINY13A_CLKI_VALIDATION_H
#include <stdint.h>

/* DS40002307A6.2.1/Table18-3, explicit datasheet-ideal-v1 fixture. Timestamps
 * denote ideal logical transitions (zero slew), not measured analog crossings.
 * No allocation, host callback, divider, waveform generation or CPU effects. */
enum {
 AT13_CLKI_VALIDATION_VOLTAGE=1u,
 AT13_CLKI_VALIDATION_HIGH=2u,
 AT13_CLKI_VALIDATION_LOW=4u,
 AT13_CLKI_VALIDATION_PERIOD=8u,
 AT13_CLKI_VALIDATION_VARIATION=16u,
 AT13_CLKI_VALIDATION_MALFORMED=32u
};
typedef struct {
 uint64_t now_ps, previous_edge_ps, previous_rise_ps, previous_period_ps;
 uint64_t comparison_rise_ps, comparison_period_ps;
 uint32_t violations;
 uint8_t level, reset_held, initialized, have_edge, have_rise;
 uint8_t have_comparison_rise, have_comparison_period;
} attiny13a_clki_validation_t;

/* All APIs return a reason bitmask: zero means success/no violation. Invalid
 * arguments/time/levels return MALFORMED and leave ALL state unchanged.
 * MAX is reserved; first actual edge must be later than initial_ps. The first
 * partial high/low span and first partial period are intentionally unknown. */
uint32_t attiny13a_clki_validation_init(attiny13a_clki_validation_t *s,
 uint64_t initial_ps,uint8_t initial_level,int reset_held);

/* Set effective recognized Reset, including when no source edges arrive.
 * State changes clear variation baselines; repeated same-state observations do
 * not clear them. Preserve physical edge/rise history for width/period checks.
 * Equal timestamps are allowed here; chronological ordering is owner-defined. */
uint32_t attiny13a_clki_validation_set_reset(attiny13a_clki_validation_t *s,
 uint64_t at_ps,int reset_held);

/* Actual alternating edge; at_ps cannot precede now or equal a physical edge.
 * Electrical violations record the observation/new history and OR sticky
 * violations, returning this edge's reasons. MALFORMED is never made sticky.
 * VCC selects completed width/period limits; owner must supply a qualified
 * conservative VCC for ALL intervals checked if supply changes between edges.
 * Reset suppresses variation comparison, never voltage/width/period limits.
 * After release, comparison requires two FULL post-reset rising periods.
 * Both2% readings: abs(curr-prev)<=min(curr,prev)/50, exact without overflow. */
uint32_t attiny13a_clki_validation_edge(attiny13a_clki_validation_t *s,
 uint64_t at_ps,uint8_t new_level,int32_t vcc_uv,int reset_held);
#endif
