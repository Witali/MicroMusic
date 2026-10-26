#include "analog_adc.h"

enum { IDLE = ANALOG_ADC_IDLE, WAIT_START, AUTO_SYNC, CONVERTING };

static uint16_t divisor(const analog_adc_t *adc) {
    uint8_t code = adc->adcsra & 7;
    return code < 2 ? 2 : (uint16_t)(1u << code);
}

static uint64_t next_edge(const analog_adc_t *adc, uint64_t now) {
    uint64_t d = divisor(adc);
    return adc->origin + ((now - adc->origin) / d + 1) * d;
}

static void begin(analog_adc_t *adc, int automatic) {
    adc->phase = CONVERTING;
    adc->elapsed = 0;
    adc->sampled = 0;
    adc->conversion_first = adc->first;
    adc->auto_conversion = automatic != 0;
    adc->selected_mux = adc->admux & 3;
    adc->selected_reference = (adc->admux >> 6) & 1;
}

static void request(analog_adc_t *adc, int automatic) {
    if (!(adc->adcsra & ANALOG_ADEN) || adc->phase != IDLE) return;
    adc->adcsra |= ANALOG_ADSC;
    adc->phase = automatic ? AUTO_SYNC : WAIT_START;
    if (automatic) {
        /* Three CPU clocks of trigger synchronizer latency (14.5). */
        adc->next_half_edge = adc->half_cycle + 6;
    } else {
        uint64_t period = 2u * divisor(adc);
        adc->next_half_edge = adc->origin +
            ((adc->half_cycle - adc->origin) / period + 1) * period;
    }
}

static int selected_flag(const analog_adc_t *adc) {
    uint8_t source = adc->adcsrb & 7;
    return source > 0 && source < 7 && (adc->source_flags & (1u << source));
}

static void trigger_change(analog_adc_t *adc, int previous) {
    if ((adc->adcsra & ANALOG_ADATE) && !previous && selected_flag(adc))
        request(adc, 1);
}

static void sample(analog_adc_t *adc) {
    uint32_t reference = adc->selected_reference ? adc->bandgap_uv : adc->vcc_uv;
    int32_t voltage = adc->channel_uv[adc->selected_mux];
    adc->invalid_reference = reference == 0;
    if (!reference || voltage <= 0) adc->sampled_result = 0;
    else {
        uint64_t scaled = (uint64_t)(uint32_t)voltage * 1024 / reference;
        adc->sampled_result = scaled > 1023 ? 1023 : (uint16_t)scaled;
    }
    adc->sampled_at = adc->half_cycle;
    adc->sampled = 1;
}

static void half_edge(analog_adc_t *adc) {
    if (adc->phase == WAIT_START) begin(adc, 0);
    else if (adc->phase == AUTO_SYNC) {
        /* Prescaler phase restarts after trigger synchronization. */
        adc->origin = adc->half_cycle;
        begin(adc, 1);
    } else {
        uint8_t sample_phase = adc->conversion_first ? adc->first_sample_half_adc :
            (adc->auto_conversion ? 4 : 3);
        uint8_t complete_phase = adc->conversion_first ? 50 :
            (adc->auto_conversion ? 27 : 26);
        ++adc->elapsed;
        if (!adc->sampled && adc->elapsed == sample_phase) sample(adc);
        if (adc->elapsed == complete_phase) {
            if (adc->data_locked) ++adc->discarded_results;
            else adc->result = adc->sampled_result;
            ++adc->conversions;
            adc->completed_at = adc->half_cycle;
            adc->adcsra |= ANALOG_ADIF;
            adc->first = 0;
            if ((adc->adcsra & ANALOG_ADATE) && !(adc->adcsrb & 7)) begin(adc, 0);
            else {
                adc->phase = IDLE;
                adc->adcsra &= (uint8_t)~ANALOG_ADSC;
            }
        }
    }
    if (adc->phase != IDLE) adc->next_half_edge = next_edge(adc, adc->half_cycle);
}

void analog_adc_reset(analog_adc_t *adc, uint32_t vcc_uv, uint32_t bandgap_uv,
                      uint8_t first_sample_half_adc, uint64_t half_cycle) {
    *adc = (analog_adc_t){0};
    adc->vcc_uv = vcc_uv;
    adc->bandgap_uv = bandgap_uv;
    adc->clock_running = 1;
    adc->first = 1;
    adc->first_sample_half_adc = first_sample_half_adc == 29 ? 29 : 27;
    adc->half_cycle = adc->origin = half_cycle;
}

uint64_t analog_adc_next_event(const analog_adc_t *adc) {
    return adc->clock_running && adc->phase != IDLE ? adc->next_half_edge : UINT64_MAX;
}

int analog_adc_advance(analog_adc_t *adc, uint64_t half_cycle) {
    if (half_cycle < adc->half_cycle) return 0;
    if (!adc->clock_running) {
        uint64_t stopped = half_cycle - adc->half_cycle;
        adc->origin += stopped;
        if (adc->phase != IDLE) adc->next_half_edge += stopped;
    }
    while (adc->clock_running && adc->phase != IDLE && adc->next_half_edge <= half_cycle) {
        adc->half_cycle = adc->next_half_edge;
        half_edge(adc);
    }
    adc->half_cycle = half_cycle;
    return 1;
}

int analog_adc_read(analog_adc_t *adc, uint8_t io, uint8_t *value, uint64_t half_cycle) {
    if (io < ANALOG_ADCSRB || io > ANALOG_ADMUX || !analog_adc_advance(adc, half_cycle)) return 0;
    uint16_t formatted = (adc->admux & 0x20) ? (uint16_t)(adc->result << 6) : adc->result;
    switch (io) {
    case ANALOG_ADCSRB: *value = adc->adcsrb; break;
    case ANALOG_ADCL: *value = (uint8_t)formatted; adc->data_locked = 1; break;
    case ANALOG_ADCH: *value = (uint8_t)(formatted >> 8); adc->data_locked = 0; break;
    case ANALOG_ADCSRA: *value = adc->adcsra; break;
    default: *value = adc->admux; break;
    }
    return 1;
}

int analog_adc_write(analog_adc_t *adc, uint8_t io, uint8_t value, uint64_t half_cycle) {
    if (io < ANALOG_ADCSRB || io > ANALOG_ADMUX || !analog_adc_advance(adc, half_cycle)) return 0;
    int previous = selected_flag(adc);
    if (io == ANALOG_ADCSRB) {
        adc->adcsrb = value & 0x47;
        trigger_change(adc, previous);
    } else if (io == ANALOG_ADMUX) adc->admux = value & 0x63;
    else if (io == ANALOG_ADCSRA) {
        uint8_t old = adc->adcsra;
        adc->adcsra = (value & (uint8_t)~(ANALOG_ADSC | ANALOG_ADIF)) |
            (old & ANALOG_ADSC) | ((old & ANALOG_ADIF) & (uint8_t)~value);
        if (!(value & ANALOG_ADEN)) {
            adc->phase = IDLE;
            adc->adcsra &= (uint8_t)~ANALOG_ADSC;
            adc->first = 1;
            adc->origin = half_cycle;
        } else {
            if (!(old & ANALOG_ADEN)) adc->origin = half_cycle;
            if (value & ANALOG_ADSC) request(adc, 0);
            else if (!(old & ANALOG_ADATE)) trigger_change(adc, 0);
            if ((old & 7) != (value & 7) && adc->phase != IDLE && adc->phase != AUTO_SYNC) {
                if (adc->phase == WAIT_START) {
                    uint64_t period = 2u * divisor(adc);
                    adc->next_half_edge = adc->origin + ((half_cycle - adc->origin) / period + 1) * period;
                } else adc->next_half_edge = next_edge(adc, half_cycle);
            }
        }
    }
    /* ADCL/ADCH are read-only. */
    return 1;
}

int analog_adc_input(analog_adc_t *adc, uint8_t channel, int32_t microvolts, uint64_t half_cycle) {
    if (channel > 3 || !analog_adc_advance(adc, half_cycle)) return 0;
    adc->channel_uv[channel] = microvolts;
    return 1;
}

int analog_adc_reference(analog_adc_t *adc, uint32_t vcc_uv, uint32_t bandgap_uv,
                          uint64_t half_cycle) {
    if (!analog_adc_advance(adc, half_cycle)) return 0;
    adc->vcc_uv = vcc_uv;
    adc->bandgap_uv = bandgap_uv;
    return 1;
}

int analog_adc_sources(analog_adc_t *adc, uint8_t flags, uint64_t half_cycle) {
    if (!analog_adc_advance(adc, half_cycle)) return 0;
    int previous = selected_flag(adc);
    adc->source_flags = flags & 0x7e;
    trigger_change(adc, previous);
    return 1;
}

int analog_adc_ack(analog_adc_t *adc, uint64_t half_cycle) {
    if (!analog_adc_advance(adc, half_cycle)) return 0;
    adc->adcsra &= (uint8_t)~ANALOG_ADIF;
    return 1;
}

int analog_adc_pending(const analog_adc_t *adc) {
    return (adc->adcsra & (ANALOG_ADIF | ANALOG_ADIE)) == (ANALOG_ADIF | ANALOG_ADIE);
}

int analog_adc_clock_running(analog_adc_t *adc, int running, uint64_t half_cycle) {
    if (!analog_adc_advance(adc, half_cycle)) return 0;
    adc->clock_running = running != 0;
    return 1;
}

int analog_adc_noise_cancel_start(analog_adc_t *adc, uint64_t half_cycle) {
    if (!analog_adc_advance(adc, half_cycle)) return 0;
    if ((adc->adcsra & (ANALOG_ADEN | ANALOG_ADATE | ANALOG_ADIE)) == (ANALOG_ADEN | ANALOG_ADIE))
        request(adc, 0);
    return 1;
}
