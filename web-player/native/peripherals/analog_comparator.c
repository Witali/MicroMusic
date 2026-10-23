#include "analog_comparator.h"

static uint64_t minimum(uint64_t a, uint64_t b) { return a < b ? a : b; }
static int disabled(const analog_comparator_t *c) {
    return (c->acsr & ANALOG_ACD) || c->sleep_disabled;
}
static uint64_t clock_after(const analog_comparator_t *c, uint64_t now) {
    uint64_t phase = c->clock_origin & 1;
    return now + ((now & 1) == phase ? 2 : 1);
}
static void sync_needed(analog_comparator_t *c) {
    if (c->clock_running && !disabled(c) &&
        (c->sync1 != c->raw || ((c->acsr & ANALOG_ACO) != 0) != c->sync1)) {
        if (c->synchronize_at == UINT64_MAX) c->synchronize_at = clock_after(c, c->half_cycle);
    } else c->synchronize_at = UINT64_MAX;
}
static void compare(analog_comparator_t *c) {
    if (disabled(c) || c->bandgap_ready_at != UINT64_MAX) {
        c->propagation_at = UINT64_MAX;
        return;
    }
    static const uint8_t channel_pin[] = {5,2,4,3};
    int64_t positive = (c->acsr & ANALOG_ACBG) ? (int64_t)c->bandgap_uv : c->pin_uv[0];
    uint8_t negative_pin = c->acme && !c->adc_enabled ? channel_pin[c->mux] : 1;
    /* An ideal tie resolves low. No offset, noise or metastability is modeled. */
    uint8_t result = positive > c->pin_uv[negative_pin];
    if (result == c->raw) c->propagation_at = UINT64_MAX;
    else if (c->propagation_at == UINT64_MAX || c->propagation_level != result) {
        c->propagation_level = result;
        c->propagation_at = c->half_cycle + c->propagation_delay;
    }
}
static void activate(analog_comparator_t *c) {
    if (disabled(c)) {
        c->propagation_at = c->synchronize_at = c->bandgap_ready_at = UINT64_MAX;
    } else {
        if ((c->acsr & ANALOG_ACBG) && c->bandgap_startup_delay)
            c->bandgap_ready_at = c->half_cycle + c->bandgap_startup_delay;
        compare(c);
        sync_needed(c);
    }
}

void analog_comparator_reset(analog_comparator_t *c, const analog_comparator_config_t *config,
                             uint32_t bandgap_uv, uint64_t half_cycle) {
    *c = (analog_comparator_t){0};
    c->half_cycle = half_cycle;
    c->clock_origin = config->clock_origin_half_cycle;
    c->propagation_delay = config->propagation_half_cycles;
    c->bandgap_startup_delay = config->bandgap_startup_half_cycles;
    c->bandgap_uv = bandgap_uv;
    c->raw = c->sync1 = config->initial_output != 0;
    c->acsr = c->raw ? ANALOG_ACO : 0;
    c->clock_running = 1;
    c->propagation_at = c->synchronize_at = c->bandgap_ready_at = UINT64_MAX;
    compare(c);
}

uint64_t analog_comparator_next_event(const analog_comparator_t *c) {
    return minimum(c->bandgap_ready_at, minimum(c->propagation_at, c->synchronize_at));
}

int analog_comparator_advance(analog_comparator_t *c, uint64_t half_cycle) {
    if (half_cycle < c->half_cycle) return 0;
    uint64_t next;
    while ((next = analog_comparator_next_event(c)) != UINT64_MAX && next <= half_cycle) {
        c->half_cycle = next;
        if (c->bandgap_ready_at == next) {
            c->bandgap_ready_at = UINT64_MAX;
            compare(c);
        }
        if (c->propagation_at == next) {
            c->propagation_at = UINT64_MAX;
            c->raw = c->propagation_level;
            sync_needed(c);
        }
        if (c->synchronize_at == next) {
            c->synchronize_at = UINT64_MAX;
            uint8_t previous = (c->acsr & ANALOG_ACO) != 0;
            uint8_t output = c->sync1;
            c->sync1 = c->raw;
            c->acsr = (c->acsr & (uint8_t)~ANALOG_ACO) | (output ? ANALOG_ACO : 0);
            if (output != previous) {
                ++c->transitions;
                uint8_t sense = c->acsr & 3;
                if (!sense || (sense == 2 && !output) || (sense == 3 && output))
                    c->acsr |= ANALOG_ACI;
            }
            sync_needed(c);
        }
    }
    c->half_cycle = half_cycle;
    return 1;
}

int analog_comparator_read(analog_comparator_t *c, uint8_t io, uint8_t *value,
                           uint64_t half_cycle) {
    if (io != ANALOG_ACSR || !analog_comparator_advance(c, half_cycle)) return 0;
    *value = c->acsr;
    return 1;
}

int analog_comparator_write(analog_comparator_t *c, uint8_t io, uint8_t value,
                            uint64_t half_cycle) {
    if (io != ANALOG_ACSR || !analog_comparator_advance(c, half_cycle)) return 0;
    uint8_t previous = c->acsr;
    if (((previous ^ value) & (ANALOG_ACD | 3)) && ((previous | value) & ANALOG_ACIE))
        ++c->unsafe_control_changes;
    c->acsr = (value & 0xcb) | (previous & ANALOG_ACO) |
        ((previous & ANALOG_ACI) & (uint8_t)~value);
    if ((previous ^ c->acsr) & ANALOG_ACD) activate(c);
    else if ((previous ^ c->acsr) & ANALOG_ACBG) {
        c->bandgap_ready_at = UINT64_MAX;
        activate(c);
    }
    return 1;
}

int analog_comparator_input(analog_comparator_t *c, uint8_t pin, int32_t microvolts,
                            uint64_t half_cycle) {
    if (pin > 5 || !analog_comparator_advance(c, half_cycle)) return 0;
    c->pin_uv[pin] = microvolts;
    compare(c);
    return 1;
}

int analog_comparator_reference(analog_comparator_t *c, uint32_t bandgap_uv,
                                uint64_t half_cycle) {
    if (!analog_comparator_advance(c, half_cycle)) return 0;
    c->bandgap_uv = bandgap_uv;
    compare(c);
    return 1;
}

int analog_comparator_adc(analog_comparator_t *c, uint8_t adcsra, uint8_t adcsrb,
                          uint8_t admux, uint64_t half_cycle) {
    if (!analog_comparator_advance(c, half_cycle)) return 0;
    c->adc_enabled = (adcsra & 0x80) != 0;
    c->acme = (adcsrb & 0x40) != 0;
    c->mux = admux & 3;
    compare(c);
    return 1;
}

int analog_comparator_pending(const analog_comparator_t *c) {
    return (c->acsr & (ANALOG_ACI | ANALOG_ACIE)) == (ANALOG_ACI | ANALOG_ACIE);
}

int analog_comparator_ack(analog_comparator_t *c, uint64_t half_cycle) {
    if (!analog_comparator_advance(c, half_cycle)) return 0;
    c->acsr &= (uint8_t)~ANALOG_ACI;
    return 1;
}

int analog_comparator_clock_running(analog_comparator_t *c, int running,
                                    uint64_t clock_origin, uint64_t half_cycle) {
    if (!analog_comparator_advance(c, half_cycle)) return 0;
    c->clock_running = running != 0;
    c->clock_origin = clock_origin;
    c->synchronize_at = UINT64_MAX;
    sync_needed(c);
    return 1;
}

int analog_comparator_sleep(analog_comparator_t *c, int is_disabled, uint64_t half_cycle) {
    if (!analog_comparator_advance(c, half_cycle)) return 0;
    if (c->sleep_disabled != (is_disabled != 0)) {
        c->sleep_disabled = is_disabled != 0;
        activate(c);
    }
    return 1;
}
