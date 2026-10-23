#ifndef MICROMUSIC_ATTINY13A_RESET_INPUT_H
#define MICROMUSIC_ATTINY13A_RESET_INPUT_H
#include <stdint.h>

#define AT13_RESET_INPUT_NEVER UINT64_MAX
enum {
 AT13_RESET_INPUT_IDLE=0, AT13_RESET_INPUT_QUALIFY=1, AT13_RESET_INPUT_PROPAGATE=2,
 AT13_RESET_INPUT_ASSERT=1, AT13_RESET_INPUT_RELEASE=2,
 AT13_RESET_INPUT_BAD_PROFILE=1, AT13_RESET_INPUT_BAD_TIME=2,
 AT13_RESET_INPUT_BAD_INPUT=4, AT13_RESET_INPUT_TIME_OVERFLOW=8
};

/* Explicit selected digital/analog fixture, not a universal chip calibration.
 * Thresholds scale with the CURRENT VCC. Their difference is the hysteresis.
 * Qualifications and propagation delays are independently supplied ps values;
 * neither is inferred from the datasheet's minimum accepted RESET pulse. */
typedef struct {
 uint32_t assert_threshold_ppm, release_threshold_ppm;
 uint64_t assert_qualification_ps, release_qualification_ps;
 uint64_t assert_propagation_ps, release_propagation_ps;
} attiny13a_reset_input_profile_t;

typedef struct {
 attiny13a_reset_input_profile_t profile;
 uint64_t now_ps, deadline_ps, last_change_ps, qualified_at_ps;
 int32_t reset_uv, vcc_uv;
 uint8_t raw_low, qualified, asserted, phase, fault, changes;
} attiny13a_reset_input_t;

/* 200000 <= assert < release <= 900000 ppm. Zero timing values are valid.
 * Timestamp UINT64_MAX is reserved for NEVER. Input voltages are signed uV;
 * negative VCC is invalid. At VCC0 the receiver is inactive/released, pending
 * work is cancelled, and POR remains the supply-reset owner's responsibility.
 * Initial band state is released; a low input begins its selected qualification.
 * init is the only operation that clears a sticky fault. */
int attiny13a_reset_input_init(attiny13a_reset_input_t *receiver,
 const attiny13a_reset_input_profile_t *profile, uint64_t at_ps,
 int32_t reset_uv, int32_t vcc_uv);
/* Atomic RESET/VCC update prevents fictitious intermediate common-mode edges.
 * Inputs are piecewise constant. Due deadlines run BEFORE an equal-time input.
 * This chosen model uses INERTIAL propagation: an opposite Schmitt transition
 * cancels qualification OR propagation before the output changes. Crossing
 * within the hysteresis band does not cancel an existing candidate. */
int attiny13a_reset_input_set_voltage(attiny13a_reset_input_t *receiver,
 uint64_t at_ps, int32_t reset_uv, int32_t vcc_uv);
/* No CPU clocks, allocations, callbacks, event ring, SUT or fuse ownership.
 * Stop at every next_deadline and sample asserted to feed the board's EXTRF
 * aggregator. A stable interval requires at most two internal state changes.
 * On fault, output freezes and next_deadline returns NEVER. */
int attiny13a_reset_input_advance(attiny13a_reset_input_t *receiver,uint64_t at_ps);
uint64_t attiny13a_reset_input_next_deadline(const attiny13a_reset_input_t *receiver);
int attiny13a_reset_input_asserted(const attiny13a_reset_input_t *receiver);
/* Optional transition-kind latch for diagnostics; it records both kinds if
 * callers batch equal-time inputs. It is not a timestamped history. Board
 * aggregation must observe deadlines and inputs in chronological order. */
uint8_t attiny13a_reset_input_take_changes(attiny13a_reset_input_t *receiver);
#endif
