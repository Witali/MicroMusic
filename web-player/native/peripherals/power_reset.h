#ifndef MICROMUSIC_ATTINY13A_POWER_RESET_H
#define MICROMUSIC_ATTINY13A_POWER_RESET_H
#include <stdint.h>
#include "../attiny13a-registers.h"

#define POWER_RESET_NEVER UINT64_MAX
#define POWER_RESET_EVENT_CAPACITY 32
enum {
    POWER_RESET_PORF=AT13_MASK_PORF, POWER_RESET_EXTRF=AT13_MASK_EXTRF,
    POWER_RESET_BORF=AT13_MASK_BORF, POWER_RESET_WDRF=AT13_MASK_WDRF,
    POWER_RESET_ASSERT=1, POWER_RESET_HOLD=2, POWER_RESET_RELEASE=3,
    POWER_RESET_BOD_OFF=4, POWER_RESET_BOD_RECOVER=5, POWER_RESET_BOD_READY=6,
    POWER_RESET_BAD_PROFILE=1, POWER_RESET_BAD_TIME=2, POWER_RESET_BAD_INPUT=3,
    POWER_RESET_TIME_OVERFLOW=4, POWER_RESET_EVENT_OVERFLOW=5
};

typedef struct {
    int32_t por_assert_uv, por_release_uv;
    /* Indexed by raw BODLEVEL fuse code 00, 01, 10. Code 11 disables BOD. */
    int32_t bod_center_uv[3], bod_hysteresis_uv;
    /* Board-chosen uniform physical time units, independent of CPU clocks.
     * timeout_ticks is the post-source reset delay; do not add it twice in the
     * device clock/startup policy. All three durations are explicit parameters. */
    uint64_t bod_filter_ticks, timeout_ticks, bod_recovery_ticks;
} power_reset_profile_t;

typedef struct {
    uint64_t at, deadline;
    uint8_t kind, sources, causes, flags_set, flags_clear;
} power_reset_event_t;

typedef struct {
    power_reset_profile_t profile;
    uint64_t now, bod_deadline, release_deadline, recovery_deadline;
    int32_t vcc_uv;
    uint8_t bod_code, por_active, bod_active, other_sources;
    uint8_t sources, causes, held, bod_sleep_off, fault;
    uint8_t head, count;
    power_reset_event_t events[POWER_RESET_EVENT_CAPACITY];
} power_reset_t;

/* Typical-voltage fixture only, NOT a chip-wide guaranteed calibration. Caller
 * supplies tBOD, tTOUT and BOD recovery in its selected physical time domain. */
void power_reset_typical_profile(power_reset_profile_t *profile,
                                uint64_t filter_ticks, uint64_t timeout_ticks,
                                uint64_t recovery_ticks);
int power_reset_init(power_reset_t *power, const power_reset_profile_t *profile,
                     uint8_t fuse_high, uint64_t at, int32_t vcc_uv);
/* Inputs are piecewise-constant and time ordered, not queued future values.
 * Scheduled deadlines at the same timestamp are processed BEFORE the input. */
int power_reset_set_vcc(power_reset_t *power, uint64_t at, int32_t vcc_uv);
/* Atomic supply + already-qualified EXTRF/WDRF update. Validate both inputs
 * before advancing/mutating state, then process due deadlines, set both inputs
 * and evaluate their aggregate once. This avoids fictitious RELEASE/ASSERT
 * gaps when ownership transfers between POR/BOD and another reset source.
 * Existing individual setters preserve the other input and use this API. */
int power_reset_set_inputs(power_reset_t *power, uint64_t at, int32_t vcc_uv,
                           uint8_t other_sources);
int power_reset_advance(power_reset_t *power, uint64_t at);
uint64_t power_reset_next_deadline(const power_reset_t *power);
/* Optional aggregation: only EXTRF/WDRF are accepted, already qualified by
 * their owners. Caller must drive pulses low again. All active sources prevent
 * tTOUT from beginning. IRQ and CPU instruction boundaries are irrelevant. */
int power_reset_set_other_sources(power_reset_t *power, uint64_t at, uint8_t mask);
/* sleep_mode is MCUCR.SM: 0 Idle, 1 ADC Noise Reduction, 2 Power-down.
 * bods_active means the timed BODCR sequence was authorized by its owner.
 * This module does not own BODCR or its CPU-clock write windows. */
int power_reset_sleep(power_reset_t *power, uint64_t at, uint8_t sleep_mode,
                       int bods_active);
int power_reset_wake(power_reset_t *power, uint64_t at);
int power_reset_execution_blocked(const power_reset_t *power);
int power_reset_bod_enabled(const power_reset_t *power);
int power_reset_pop_event(power_reset_t *power, power_reset_event_t *event);
/* Errata DS80000857A2.2.1: a condition to report to the NVM owner, not a
 * fabricated deterministic failure, random corruption, or automatic erase. */
int power_reset_eeprom_voltage_uncertain(const power_reset_t *power);
#endif
