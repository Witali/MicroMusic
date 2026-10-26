#ifndef MICROMUSIC_TINY13_ANALOG_COMPARATOR_H
#define MICROMUSIC_TINY13_ANALOG_COMPARATOR_H

#include <stdint.h>
#include "../attiny13a-registers.h"

enum {
    ANALOG_ACSR = AT13_IO_ACSR, ANALOG_ACD = AT13_MASK_ACD, ANALOG_ACBG = AT13_MASK_ACBG,
    ANALOG_ACO = AT13_MASK_ACO, ANALOG_ACI = AT13_MASK_ACI, ANALOG_ACIE = AT13_MASK_ACIE
};
enum {
    ANALOG_COMPARATOR_PHYSICAL_NONE = 0,
    ANALOG_COMPARATOR_PHYSICAL_TIME_REVERSED = 1,
    ANALOG_COMPARATOR_PHYSICAL_DEADLINE_OVERFLOW = 2,
    ANALOG_COMPARATOR_PHYSICAL_CONFIG = 3
};

typedef struct {
    /* Explicit fixture parameters, in HALF CPU clock periods. The digital
     * two-stage synchronizer adds a phase-dependent 1..2 CPU clock periods. */
    uint32_t propagation_half_cycles, bandgap_startup_half_cycles;
    uint64_t clock_origin_half_cycle;
    uint8_t initial_output; /* Hardware ACO reset is unspecified. */
} analog_comparator_config_t;

typedef struct {
    uint64_t half_cycle, propagation_at, synchronize_at, bandgap_ready_at;
    uint64_t clock_origin, transitions, unsafe_control_changes;
    uint32_t propagation_delay, bandgap_startup_delay, bandgap_uv;
    int32_t pin_uv[6];
    uint8_t acsr, adc_enabled, acme, mux;
    uint8_t raw, propagation_level, sync1, clock_running, sleep_disabled;
    /* Optional separate wall domain. UINT64_MAX remains the no-event sentinel.
     * Faults are sticky until reset, including rejected late configuration. */
    uint64_t physical_time_ps, propagation_at_ps, bandgap_ready_at_ps;
    uint64_t propagation_delay_ps, bandgap_startup_delay_ps;
    uint8_t physical_enabled, physical_fault, physical_configurable;
    /* 0: unavailable, 1: reset epoch-zero rise eligible, 2: already observed. */
    uint8_t physical_first_rise;
} analog_comparator_t;

/* Clock-stamped APIs use HALF CPU/clkI/O periods; cycle N is timestamp2*N,
 * identical to analog_adc. Explicit *_ps APIs below use physical picoseconds.
 * Timestamped calls advance THROUGH their domain time before mutation. */
void analog_comparator_reset(analog_comparator_t *comparator,
                             const analog_comparator_config_t *config,
                             uint32_t bandgap_uv, uint64_t half_cycle);
/* Select immediately after reset, before any public advance/read/mutation. The
 * reset half-cycle epoch may be arbitrary. Preserve the supplied reset output
 * and replace its initial legacy raw deadline using explicit physical ns. */
int analog_comparator_configure_physical(analog_comparator_t *comparator,
                                         uint32_t propagation_ns,
                                         uint32_t startup_ns, uint64_t now_ps);
/* Physical analog progress never delivers digital phases. Advance the existing
 * half timeline to the pre-edge anchor first, call advance_ps THROUGH wall time,
 * then deliver the eligible half edge. Before an input/register mutation, call
 * advance_ps first, then the ordinary API at its delivered half-cycle instant.
 * This preserves analog-before-clock and existing-events-before-input ties. */
int analog_comparator_advance_ps(analog_comparator_t *comparator, uint64_t now_ps);
uint64_t analog_comparator_next_event_ps(const analog_comparator_t *comparator);
/* Initial-low CLKI may deliver its first actual rise at half epoch zero. Arm
 * pending stages there, without delivering the edge; the next advance(0)
 * performs that sample. Physical mode, half0 and a running digital clock are
 * required. Repeated calls at half0 are idempotent, even after that sample.
 * ACD/sleep-disabled comparators consume eligibility without sampling. */
int analog_comparator_arm_first_rise(analog_comparator_t *comparator);
/* In physical mode this advances digital synchronization only. */
int analog_comparator_advance(analog_comparator_t *comparator, uint64_t half_cycle);
uint64_t analog_comparator_next_event(const analog_comparator_t *comparator);
int analog_comparator_read(analog_comparator_t *comparator, uint8_t io,
                           uint8_t *value, uint64_t half_cycle);
int analog_comparator_write(analog_comparator_t *comparator, uint8_t io,
                            uint8_t value, uint64_t half_cycle);
/* Physical PB0..PB5 voltages. AIN0=PB0, AIN1=PB1; ADC0..3=PB5,PB2,PB4,PB3. */
int analog_comparator_input(analog_comparator_t *comparator, uint8_t pin,
                            int32_t microvolts, uint64_t half_cycle);
int analog_comparator_reference(analog_comparator_t *comparator,
                                uint32_t bandgap_uv, uint64_t half_cycle);
/* ADC owns these registers. Forward its current state after writes; only
 * ADEN, ACME and MUX[1:0] affect comparator input selection. */
int analog_comparator_adc(analog_comparator_t *comparator, uint8_t adcsra,
                          uint8_t adcsrb, uint8_t admux, uint64_t half_cycle);
int analog_comparator_pending(const analog_comparator_t *comparator);
int analog_comparator_ack(analog_comparator_t *comparator, uint64_t half_cycle);
int analog_comparator_clock_running(analog_comparator_t *comparator, int running,
                                    uint64_t clock_origin, uint64_t half_cycle);
/* System sleep owns the automatic disable in Power-down. This leaves ACD
 * readable as written and preserves the last ACO (unspecified on hardware). */
int analog_comparator_sleep(analog_comparator_t *comparator, int disabled,
                            uint64_t half_cycle);

#endif
