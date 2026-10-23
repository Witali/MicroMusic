#ifndef MICROMUSIC_TINY13_ANALOG_H
#define MICROMUSIC_TINY13_ANALOG_H

#include "analog_adc.h"
#include "analog_comparator.h"

typedef struct {
    analog_adc_t adc;
    analog_comparator_t comparator;
    uint8_t external_flags;
} analog_t;

/* A small in-C scheduler joining comparator ACI to ADC auto-trigger source1.
 * DIDR0 and all digital pin handling remain owned by system_gpio. */
void analog_reset(analog_t *analog, uint32_t vcc_uv, uint32_t bandgap_uv,
                   uint8_t first_sample_half_adc,
                   const analog_comparator_config_t *config, uint64_t half_cycle);
int analog_advance(analog_t *analog, uint64_t half_cycle);
uint64_t analog_next_event(const analog_t *analog);
int analog_read(analog_t *analog, uint8_t io, uint8_t *value, uint64_t half_cycle);
int analog_write(analog_t *analog, uint8_t io, uint8_t value, uint64_t half_cycle);
int analog_input(analog_t *analog, uint8_t pb_pin, int32_t microvolts, uint64_t half_cycle);
int analog_reference(analog_t *analog, uint32_t vcc_uv, uint32_t bandgap_uv, uint64_t half_cycle);
/* Only bits2..6 are external: comparator source1 is routed internally. */
int analog_sources(analog_t *analog, uint8_t flags, uint64_t half_cycle);
/* Bit N corresponds to vector word N: comparator5, ADC9. CPU owns SREG.I. */
uint16_t analog_pending(const analog_t *analog);
int analog_ack(analog_t *analog, uint8_t vector_word, uint64_t half_cycle);

#endif
