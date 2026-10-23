#ifndef MICROMUSIC_TINY13_ANALOG_ADC_H
#define MICROMUSIC_TINY13_ANALOG_ADC_H

#include <stdint.h>
#include "../attiny13a-registers.h"

/* DS40002307A chapter 14. Addresses are I/O offsets, not data addresses. */
enum {
    ANALOG_ADCSRB = AT13_IO_ADCSRB, ANALOG_ADCL = AT13_IO_ADCL, ANALOG_ADCH = AT13_IO_ADCH,
    ANALOG_ADCSRA = AT13_IO_ADCSRA, ANALOG_ADMUX = AT13_IO_ADMUX,
    ANALOG_ADEN = AT13_MASK_ADEN, ANALOG_ADSC = AT13_MASK_ADSC, ANALOG_ADATE = AT13_MASK_ADATE,
    ANALOG_ADIF = AT13_MASK_ADIF, ANALOG_ADIE = AT13_MASK_ADIE,
    ANALOG_TRIGGER_COMPARATOR = 1, ANALOG_TRIGGER_INT0 = 2,
    ANALOG_TRIGGER_COMPA = 3, ANALOG_TRIGGER_OVERFLOW = 4,
    ANALOG_TRIGGER_COMPB = 5, ANALOG_TRIGGER_PCINT = 6
};

typedef struct {
    /* CPU time domain: one unit = HALF of one unprescaled CPU/clkADC-input
     * clock period, NOT half an ADC-prescaled period. cycle N = half_cycle 2*N.
     * Use a monotonically increasing virtual domain if CPU frequency changes. */
    uint64_t half_cycle, origin, next_half_edge;
    uint64_t conversions, discarded_results, sampled_at, completed_at;
    int32_t channel_uv[4];
    uint32_t vcc_uv, bandgap_uv;
    uint16_t result, sampled_result;
    uint8_t adcsra, adcsrb, admux, source_flags;
    uint8_t phase, elapsed, first, conversion_first, auto_conversion;
    uint8_t selected_mux, selected_reference, sampled, data_locked;
    uint8_t clock_running, first_sample_half_adc, invalid_reference;
} analog_adc_t;

/* Supply/reference are explicit fixture parameters; no nominal analog values
 * are invented. first_sample_half_adc must be 27 or 29: see README ambiguity. */
void analog_adc_reset(analog_adc_t *adc, uint32_t vcc_uv, uint32_t bandgap_uv,
                      uint8_t first_sample_half_adc, uint64_t half_cycle);
/* All timestamped calls advance events THROUGH the timestamp before mutation.
 * Equal-time voltage injection therefore follows sampling at that timestamp.
 * Calls with time earlier than the current time are rejected (return zero). */
int analog_adc_advance(analog_adc_t *adc, uint64_t half_cycle);
uint64_t analog_adc_next_event(const analog_adc_t *adc);
int analog_adc_read(analog_adc_t *adc, uint8_t io, uint8_t *value, uint64_t half_cycle);
int analog_adc_write(analog_adc_t *adc, uint8_t io, uint8_t value, uint64_t half_cycle);
int analog_adc_input(analog_adc_t *adc, uint8_t channel, int32_t microvolts,
                      uint64_t half_cycle);
int analog_adc_reference(analog_adc_t *adc, uint32_t vcc_uv, uint32_t bandgap_uv,
                          uint64_t half_cycle);
/* Flags use bit (1 << ADTS): supply current interrupt FLAG levels, independent
 * of interrupt enables. Held flags do not retrigger; source 7 is reserved. */
int analog_adc_sources(analog_adc_t *adc, uint8_t flags, uint64_t half_cycle);
int analog_adc_ack(analog_adc_t *adc, uint64_t half_cycle);
int analog_adc_pending(const analog_adc_t *adc);
/* Gate the source clock for sleep/PRR; retaining phase shifts deadlines by the
 * stopped interval. ADC Noise Reduction retains this clock. No CPU execution
 * or sleep wakeup is performed here. */
int analog_adc_clock_running(analog_adc_t *adc, int running, uint64_t half_cycle);
int analog_adc_noise_cancel_start(analog_adc_t *adc, uint64_t half_cycle);

#endif
