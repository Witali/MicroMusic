#ifndef MICROMUSIC_TINY13_SYSTEM_GPIO_H
#define MICROMUSIC_TINY13_SYSTEM_GPIO_H

#include <stdint.h>
#include "../attiny13a-registers.h"

/* ATtiny13A DS40002307A sections 9, 10 and 12.3. I/O offsets, not SRAM addresses. */
enum {
    SYSTEM_DIDR0 = AT13_IO_DIDR0, SYSTEM_PCMSK = AT13_IO_PCMSK, SYSTEM_PINB = AT13_IO_PINB,
    SYSTEM_DDRB = AT13_IO_DDRB, SYSTEM_PORTB = AT13_IO_PORTB, SYSTEM_MCUCR = AT13_IO_MCUCR,
    SYSTEM_GIFR = AT13_IO_GIFR, SYSTEM_GIMSK = AT13_IO_GIMSK,
    SYSTEM_INT0 = AT13_MASK_INT0, SYSTEM_PCINT = AT13_MASK_PCIE,
    SYSTEM_T0_RISING = 1, SYSTEM_T0_FALLING = 2
};

typedef struct {
    uint64_t half_cycle;
    uint8_t levels;       /* Resolved six physical pin levels. */
    uint8_t driven;       /* Strong output-driver mask. */
    uint8_t pullups;      /* Enabled weak pull-ups, including RESET. */
    uint8_t floating;     /* No strong driver, external level or pull-up. */
    uint8_t contention;   /* Opposing strong external and internal drivers. */
} system_gpio_pins_t;

typedef struct {
    uint8_t portb, ddrb, pinb, didr0, pcmsk, gimsk, gifr, mcucr;
    uint8_t external_mask, external_levels, floating_levels;
    uint8_t override_mask, override_levels;
    uint8_t reset_pin_enabled, power_down, io_running, clock_high;
    uint8_t digital, latch, pcint_previous, pcint_edge;
    uint8_t int0_previous, t0_sync1, t0_sync2, t0_previous;
    system_gpio_pins_t pins;
} system_gpio_t;

typedef struct {
    uint64_t half_cycle;
    uint8_t edge;
} system_gpio_t0_event_t;

/* reset_pin_enabled is true for the normal unprogrammed RSTDISBL fuse.
 * Floating pins resolve to the caller's chosen fixture level, initially zero.
 * This is a digital model: contention is reported, never an analog simulation. */
void system_gpio_reset(system_gpio_t *gpio, int reset_pin_enabled);
int system_gpio_read(const system_gpio_t *gpio, uint8_t io, uint8_t *value);
int system_gpio_write(system_gpio_t *gpio, uint8_t io, uint8_t value, uint64_t half_cycle);
/* For SBI/CBI, write_mask is exactly the selected bit and value contains that
 * bit's new value. Never synthesize a read/modify/write of PINB or W1C flags. */
int system_gpio_write_masked(system_gpio_t *gpio, uint8_t io, uint8_t value,
                             uint8_t write_mask, uint64_t half_cycle);
void system_gpio_external(system_gpio_t *gpio, uint8_t driven_mask, uint8_t levels,
                          uint64_t half_cycle);
void system_gpio_floating(system_gpio_t *gpio, uint8_t levels, uint64_t half_cycle);
/* OC0A/B override PORTB0/1, but DDRB still controls the output driver. */
void system_gpio_timer_outputs(system_gpio_t *gpio, uint8_t enabled, uint8_t levels,
                               uint64_t half_cycle);
/* Power-down clamps unused digital buffers; stopping clkI/O freezes synchronizers.
 * Call before entering/leaving sleep. ADC Noise Reduction stops clkI/O without
 * asserting power_down; Idle leaves clkI/O running. */
void system_gpio_sleep(system_gpio_t *gpio, int io_running, int power_down,
                       uint64_t half_cycle);
/* Advance one actual clkI/O edge, at an explicit timestamp in half-cycle units.
 * Apply external changes before/after this call to specify phase at the edge.
 * Returns a synchronized T0 edge at the cycle where the timer must count it.
 * The caller can forward it directly to timer0_external_edge in C/WASM. */
uint8_t system_gpio_clock(system_gpio_t *gpio, int rising, uint64_t half_cycle);
/* Input/register-stable span, with rising clkI/O edges at even half_cycle.
 * Consumes edges in (begin_half_cycle,end_half_cycle]. Runs at most eight
 * half-edges before skipping an arbitrarily long settled span in O(1).
 * events must hold four entries, or may be null to deliberately discard T0.
 * Returns 0..4 events; 255 means backward time. Split spans at all injections,
 * register changes and interrupt arbitration boundaries. */
uint8_t system_gpio_advance(system_gpio_t *gpio, uint64_t begin_half_cycle,
                            uint64_t end_half_cycle, system_gpio_t0_event_t *events);
int system_gpio_settled(const system_gpio_t *gpio);
/* First possible synchronization event, or UINT64_MAX for stable/no clkI/O. */
uint64_t system_gpio_next_event_half(const system_gpio_t *gpio, uint64_t after_half_cycle);
/* Returns GIMSK bit positions. CPU owns SREG.I, priority and entry latency. */
uint8_t system_gpio_pending(const system_gpio_t *gpio);
void system_gpio_ack(system_gpio_t *gpio, uint8_t vector_word);

#endif
