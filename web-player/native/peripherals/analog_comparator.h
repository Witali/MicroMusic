#ifndef MICROMUSIC_TINY13_ANALOG_COMPARATOR_H
#define MICROMUSIC_TINY13_ANALOG_COMPARATOR_H

#include <stdint.h>
#include "../attiny13a-registers.h"

enum {
    ANALOG_ACSR = AT13_IO_ACSR, ANALOG_ACD = AT13_MASK_ACD, ANALOG_ACBG = AT13_MASK_ACBG,
    ANALOG_ACO = AT13_MASK_ACO, ANALOG_ACI = AT13_MASK_ACI, ANALOG_ACIE = AT13_MASK_ACIE
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
} analog_comparator_t;

/* All times are HALF CPU/clkI/O periods; cycle N is timestamp2*N, identical to
 * analog_adc. Timestamped calls advance THROUGH time before mutation. */
void analog_comparator_reset(analog_comparator_t *comparator,
                             const analog_comparator_config_t *config,
                             uint32_t bandgap_uv, uint64_t half_cycle);
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
