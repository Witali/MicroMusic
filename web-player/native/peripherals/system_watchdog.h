#ifndef MICROMUSIC_TINY13_SYSTEM_WATCHDOG_H
#define MICROMUSIC_TINY13_SYSTEM_WATCHDOG_H

#include <stdint.h>

enum {
    SYSTEM_WDTCR = 0x21, SYSTEM_MCUSR = 0x34,
    SYSTEM_WDTIF = 0x80, SYSTEM_WDTIE = 0x40, SYSTEM_WDCE = 0x10, SYSTEM_WDE = 8,
    SYSTEM_WDRF = 8, SYSTEM_BORF = 4, SYSTEM_EXTRF = 2, SYSTEM_PORF = 1,
    SYSTEM_WDT_NONE = 0, SYSTEM_WDT_INTERRUPT = 1, SYSTEM_WDT_RESET = 2,
    SYSTEM_WDT_RESERVED = 4, SYSTEM_WDT_TIME_REVERSED = 8
};

typedef struct {
    uint64_t oscillator_tick, cpu_cycle, unlock_until, last_event_tick;
    uint32_t counter;
    uint8_t control, mcusr, always_on, combined_pending, reset_requested;
} system_watchdog_t;

/* always_on models the programmed WDTON fuse. Power-on sets MCUSR.PORF. */
void system_watchdog_init(system_watchdog_t *watchdog, int always_on);
/* Call when the core actually applies a reset. PORF clears older reset flags;
 * other sources accumulate, and WDRF forces WDE until software clears WDRF. */
void system_watchdog_reset(system_watchdog_t *watchdog, uint8_t sources,
                           uint64_t cpu_cycle, uint64_t oscillator_tick);
uint32_t system_watchdog_period(const system_watchdog_t *watchdog);
uint32_t system_watchdog_until_timeout(const system_watchdog_t *watchdog);
/* Independent clocks: cpu_cycle clocks the four-cycle write window;
 * oscillator_tick counts actual WDT oscillator pulses, nominally 128 kHz.
 * Do not derive the latter from instruction count or a fixed CPU divisor.
 * Stops exactly at a reset event so the core can reset all peripherals there.
 * Calling with a target past an interrupt without servicing it can cause the
 * second-timeout reset, as on hardware. Pure interrupt mode batches in O(1). */
uint8_t system_watchdog_advance(system_watchdog_t *watchdog, uint64_t cpu_cycle,
                                uint64_t oscillator_tick);
int system_watchdog_read(system_watchdog_t *watchdog, uint8_t io,
                         uint64_t cpu_cycle, uint8_t *value);
/* Advance oscillator time before bus writes at that same emulated instant. */
int system_watchdog_write(system_watchdog_t *watchdog, uint8_t io, uint8_t value,
                          uint8_t write_mask, uint64_t cpu_cycle);
void system_watchdog_wdr(system_watchdog_t *watchdog);
int system_watchdog_pending(const system_watchdog_t *watchdog);
void system_watchdog_ack(system_watchdog_t *watchdog);

#endif
