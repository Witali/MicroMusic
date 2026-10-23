#include "system_gpio.h"

enum { PIN_MASK = 0x3f, INT0_PIN = 2, T0_PIN = 4, RESET_PIN = 0x20 };

static uint8_t input_enabled(const system_gpio_t *g) {
    /* DIDR0 pin order is ADC0/PB5, ADC2/PB4, ADC3/PB3, ADC1/PB2, AIN1/1, AIN0/0. */
    uint8_t enabled = (uint8_t)~g->didr0 & PIN_MASK;
    if (g->reset_pin_enabled) enabled &= (uint8_t)~RESET_PIN;
    if (g->power_down) {
        uint8_t wake = (g->gimsk & SYSTEM_PCINT) ? g->pcmsk : 0;
        if (g->gimsk & SYSTEM_INT0) wake |= INT0_PIN;
        enabled &= wake;
    }
    return enabled;
}

static void resolve(system_gpio_t *g, uint64_t at) {
    uint8_t old_digital = g->digital;
    uint8_t driven = g->ddrb & PIN_MASK;
    uint8_t output = (g->portb & (uint8_t)~g->override_mask) |
                     (g->override_levels & g->override_mask);
    uint8_t pullup = (g->mcucr & 0x40) ? 0 : (g->portb & (uint8_t)~driven);
    if (g->reset_pin_enabled) {
        driven &= (uint8_t)~RESET_PIN;
        pullup |= RESET_PIN;
    }
    uint8_t floating = (uint8_t)~(driven | g->external_mask | pullup) & PIN_MASK;
    uint8_t levels = ((output & driven) |
                     (g->external_levels & g->external_mask & (uint8_t)~driven) |
                     (pullup & (uint8_t)~(driven | g->external_mask)) |
                     (g->floating_levels & floating)) & PIN_MASK;
    uint8_t contention = driven & g->external_mask & (output ^ g->external_levels);
    if (g->pins.levels != levels || g->pins.driven != driven ||
        g->pins.pullups != pullup || g->pins.floating != floating ||
        g->pins.contention != contention) g->pins.half_cycle = at;
    g->pins.levels = levels;
    g->pins.driven = driven;
    g->pins.pullups = pullup & PIN_MASK;
    g->pins.floating = floating;
    g->pins.contention = contention;
    g->digital = levels & input_enabled(g);
    if (g->clock_high && g->io_running) g->latch = g->digital;
    /* PCINT wake detection remains active with clkI/O stopped. While running,
     * Figure 9-1's latch/synchronizer/detector/flag path is clocked below. */
    if (!g->io_running && ((old_digital ^ g->digital) & g->pcmsk))
        g->gifr |= SYSTEM_PCINT;
    if (!(g->mcucr & 3)) g->gifr &= (uint8_t)~SYSTEM_INT0;
}

void system_gpio_reset(system_gpio_t *g, int reset_pin_enabled) {
    *g = (system_gpio_t){0};
    g->reset_pin_enabled = !!reset_pin_enabled;
    g->io_running = 1;
    g->clock_high = 1;
    resolve(g, 0);
}

int system_gpio_read(const system_gpio_t *g, uint8_t io, uint8_t *value) {
    switch (io) {
        case SYSTEM_DIDR0: *value = g->didr0; break;
        case SYSTEM_PCMSK: *value = g->pcmsk; break;
        case SYSTEM_PINB: *value = g->pinb; break;
        case SYSTEM_DDRB: *value = g->ddrb; break;
        case SYSTEM_PORTB: *value = g->portb; break;
        case SYSTEM_MCUCR: *value = g->mcucr; break;
        case SYSTEM_GIFR: *value = g->gifr; break;
        case SYSTEM_GIMSK: *value = g->gimsk; break;
        default: return 0;
    }
    return 1;
}

int system_gpio_write_masked(system_gpio_t *g, uint8_t io, uint8_t value,
                             uint8_t mask, uint64_t at) {
    uint8_t previous;
    if (!system_gpio_read(g, io, &previous)) return 0;
    uint8_t merged = (previous & (uint8_t)~mask) | (value & mask);
    switch (io) {
        case SYSTEM_DIDR0: g->didr0 = merged & PIN_MASK; break;
        case SYSTEM_PCMSK: g->pcmsk = merged & PIN_MASK; break;
        case SYSTEM_PINB: g->portb ^= value & mask & PIN_MASK; break;
        case SYSTEM_DDRB: g->ddrb = merged & PIN_MASK; break;
        case SYSTEM_PORTB: g->portb = merged & PIN_MASK; break;
        case SYSTEM_MCUCR: g->mcucr = merged & 0x7b; break;
        case SYSTEM_GIFR: g->gifr &= (uint8_t)~(value & mask); break;
        case SYSTEM_GIMSK: g->gimsk = merged & 0x60; break;
        default: return 0;
    }
    resolve(g, at);
    return 1;
}

int system_gpio_write(system_gpio_t *g, uint8_t io, uint8_t value, uint64_t at) {
    return system_gpio_write_masked(g, io, value, 0xff, at);
}

void system_gpio_external(system_gpio_t *g, uint8_t driven_mask, uint8_t levels,
                          uint64_t at) {
    g->external_mask = driven_mask & PIN_MASK;
    g->external_levels = levels & PIN_MASK;
    resolve(g, at);
}

void system_gpio_floating(system_gpio_t *g, uint8_t levels, uint64_t at) {
    g->floating_levels = levels & PIN_MASK;
    resolve(g, at);
}

void system_gpio_timer_outputs(system_gpio_t *g, uint8_t enabled, uint8_t levels,
                               uint64_t at) {
    g->override_mask = enabled & 3;
    g->override_levels = levels & 3;
    resolve(g, at);
}

void system_gpio_sleep(system_gpio_t *g, int io_running, int power_down, uint64_t at) {
    g->io_running = !!io_running;
    g->power_down = !!power_down;
    resolve(g, at);
}

uint8_t system_gpio_clock(system_gpio_t *g, int rising, uint64_t at) {
    (void)at; /* T0 result belongs to precisely the caller's supplied timestamp. */
    if (!g->io_running) return 0;
    uint8_t edge = 0;
    if (rising) {
        /* Evaluate old register outputs, then clock their successors. */
        if (g->pcint_edge) g->gifr |= SYSTEM_PCINT;
        uint8_t pcint_signal = g->pinb & g->pcmsk;
        g->pcint_edge = pcint_signal ^ g->pcint_previous;
        g->pcint_previous = pcint_signal;
        uint8_t int0 = !!(g->pinb & INT0_PIN);
        uint8_t sense = g->mcucr & 3;
        if ((sense == 1 && int0 != g->int0_previous) ||
            (sense == 2 && !int0 && g->int0_previous) ||
            (sense == 3 && int0 && !g->int0_previous)) g->gifr |= SYSTEM_INT0;
        g->int0_previous = int0;
        if (g->t0_sync2 != g->t0_previous)
            edge = g->t0_sync2 ? SYSTEM_T0_RISING : SYSTEM_T0_FALLING;
        g->t0_previous = g->t0_sync2;
        g->t0_sync2 = g->t0_sync1;
        g->t0_sync1 = !!(g->latch & T0_PIN);
        g->pinb = g->latch & input_enabled(g);
        g->clock_high = 1;
        g->latch = g->digital;
    } else {
        g->latch = g->digital;
        g->clock_high = 0;
    }
    return edge;
}

uint8_t system_gpio_pending(const system_gpio_t *g) {
    uint8_t pending = g->gifr;
    if (!(g->mcucr & 3) && !(g->digital & INT0_PIN)) pending |= SYSTEM_INT0;
    return pending & g->gimsk;
}

void system_gpio_ack(system_gpio_t *g, uint8_t vector_word) {
    if (vector_word == 1) g->gifr &= (uint8_t)~SYSTEM_INT0;
    if (vector_word == 2) g->gifr &= (uint8_t)~SYSTEM_PCINT;
}
