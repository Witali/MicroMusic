/* Host-only exact streaming statistics; never linked into AVR firmware.
 * Durations are non-overlapping producer intervals in simulator CPU cycles.
 */
#ifndef LPX_PROFILE_DURATIONS_H
#define LPX_PROFILE_DURATIONS_H
#include <stdint.h>
#include <string.h>
typedef struct {
    uint64_t count, total, maximum;
    uint64_t ring[160], sums[3], maxima[3];
    unsigned cursor;
} LpxProfileDurations;
static inline void lpx_profile_durations_init(LpxProfileDurations* state) {
    memset(state, 0, sizeof(*state));
}
/* Return zero without changing state if 64-bit totals would overflow. */
static inline int lpx_profile_durations_push(LpxProfileDurations* state, uint64_t duration) {
    static const unsigned widths[3] = {40,80,160};
    if (state->count == UINT64_MAX || duration > UINT64_MAX-state->total) return 0;
    state->total += duration;
    if (duration > state->maximum) state->maximum = duration;
    for (unsigned i=0;i<3;++i) {
        state->sums[i] += duration;
        if (state->count >= widths[i])
            state->sums[i] -= state->ring[(state->cursor+160-widths[i])%160];
        if (state->count+1 >= widths[i] && state->sums[i] > state->maxima[i])
            state->maxima[i] = state->sums[i];
    }
    state->ring[state->cursor] = duration;
    state->cursor = (state->cursor+1)%160;
    ++state->count;
    return 1;
}
#endif
