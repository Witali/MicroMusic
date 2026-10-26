#ifndef MICROMUSIC_ATTINY13A_BANDGAP_H
#define MICROMUSIC_ATTINY13A_BANDGAP_H
#include <stdint.h>

#define AT13_BANDGAP_NEVER UINT64_MAX
enum {
    AT13_BANDGAP_ADC = 1, AT13_BANDGAP_COMPARATOR = 2, AT13_BANDGAP_BOD = 4,
    AT13_BANDGAP_BAD_TIME = 1, AT13_BANDGAP_BAD_INPUT = 2,
    AT13_BANDGAP_TIME_OVERFLOW = 3
};
typedef struct {
    uint64_t now_ps, ready_at_ps, startup_ps;
    uint8_t owner_mask, powered, enabled, ready, fault;
} attiny13a_bandgap_t;

/* Explicit shared-reference digital fixture, not a voltage/temperature curve.
 * Loss of every owner or qualified power invalidates readiness immediately;
 * no residual-charge retention is inferred. Continuous owner handoffs retain
 * startup progress. Board ownership and qualified POR power are supplied here;
 * this controller does not drive BOD receivers, RESET sources or clock edges.
 * Events through now precede mutations, including equality. Zero startup is
 * an explicit ideal fixture; all delays are integer ns, all times uint64 ps.
 * UINT64_MAX is reserved. Faults are sticky until init. */
int attiny13a_bandgap_init(attiny13a_bandgap_t *state, uint32_t startup_ns,
                          uint64_t now_ps);
int attiny13a_bandgap_set(attiny13a_bandgap_t *state, uint32_t owner_mask,
                         int powered, uint64_t now_ps);
int attiny13a_bandgap_advance(attiny13a_bandgap_t *state, uint64_t now_ps);
uint64_t attiny13a_bandgap_next_event(const attiny13a_bandgap_t *state);
#endif
