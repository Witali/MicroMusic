#include "system_sleep.h"

void system_sleep_reset(system_sleep_t *s, uint64_t now) {
    *s = (system_sleep_t){0};
    s->now = now;
    s->startup_until = UINT64_MAX;
    s->ready_at = UINT64_MAX;
}

uint8_t system_sleep_enter(system_sleep_t *s, uint8_t mcucr, uint64_t now) {
    if (now < s->now) return SYSTEM_SLEEP_INVALID_TIME;
    if (s->phase != SYSTEM_SLEEP_RUNNING) return SYSTEM_SLEEP_BUSY;
    if (!(mcucr & 0x20)) {
        s->now = now;
        return SYSTEM_SLEEP_NO_CHANGE;
    }
    uint8_t mode = (mcucr >> 3) & 3;
    if (mode == 3) return SYSTEM_SLEEP_RESERVED;
    s->now = now;
    s->sleep_at = now;
    s->mode = mode;
    s->phase = SYSTEM_SLEEP_ASLEEP;
    s->wake_sources = 0;
    s->startup_until = UINT64_MAX;
    s->ready_at = UINT64_MAX;
    return SYSTEM_SLEEP_ENTERED;
}

uint16_t system_sleep_wake_mask(uint8_t mode, int int0_level_sense) {
    uint16_t mask;
    if (mode == SYSTEM_SLEEP_IDLE) return 0x3ff;
    if (mode == SYSTEM_SLEEP_ADC_NOISE)
        mask = SYSTEM_WAKE_RESET | SYSTEM_WAKE_PCINT | SYSTEM_WAKE_NVM_READY |
               SYSTEM_WAKE_WDT | SYSTEM_WAKE_ADC;
    else if (mode == SYSTEM_SLEEP_POWER_DOWN)
        mask = SYSTEM_WAKE_RESET | SYSTEM_WAKE_PCINT | SYSTEM_WAKE_WDT;
    else return 0;
    if (int0_level_sense) mask |= SYSTEM_WAKE_INT0;
    return mask;
}

uint8_t system_sleep_wake(system_sleep_t *s, uint16_t asserted, uint16_t enabled,
                          int int0_level_sense, system_sleep_timing_t timing,
                          uint64_t now) {
    uint64_t extra=(!timing.ticks_per_cpu_cycle ||
        timing.ticks_per_cpu_cycle > UINT64_MAX / SYSTEM_SLEEP_EXTRA_WAKE_CYCLES) ? 0 :
        timing.ticks_per_cpu_cycle*SYSTEM_SLEEP_EXTRA_WAKE_CYCLES;
    return system_sleep_wake_exact(s,asserted,enabled,int0_level_sense,
        timing.startup_ticks,extra,now);
}

uint8_t system_sleep_wake_exact(system_sleep_t *s,uint16_t asserted,uint16_t enabled,
                               int int0_level_sense,uint64_t startup_ticks,
                               uint64_t extra_ticks,uint64_t now) {
    if (now < s->now) return SYSTEM_SLEEP_INVALID_TIME;
    if (asserted & SYSTEM_WAKE_RESET) {
        system_sleep_reset(s, now);
        s->wake_sources = SYSTEM_WAKE_RESET;
        return SYSTEM_SLEEP_RESET;
    }
    if (s->phase != SYSTEM_SLEEP_ASLEEP) {
        s->now = now;
        return SYSTEM_SLEEP_NO_CHANGE;
    }
    uint16_t sources = asserted & enabled & system_sleep_wake_mask(s->mode, int0_level_sense);
    if (!sources) {
        s->now = now;
        return SYSTEM_SLEEP_NO_CHANGE;
    }
    /* Reject invalid/overflowing deadlines before changing the sleeping state. */
    if (!extra_ticks || startup_ticks > UINT64_MAX - now)
        return SYSTEM_SLEEP_INVALID_TIME;
    uint64_t startup_until = now + startup_ticks;
    if (extra_ticks > UINT64_MAX - startup_until) return SYSTEM_SLEEP_INVALID_TIME;
    s->now = now;
    s->wake_at = now;
    s->wake_sources = sources;
    s->startup_until = startup_until;
    s->ready_at = startup_until + extra_ticks;
    s->phase = startup_ticks ? SYSTEM_SLEEP_STARTING : SYSTEM_SLEEP_WAKE_DELAY;
    return SYSTEM_SLEEP_WAKE_STARTED;
}

uint8_t system_sleep_advance(system_sleep_t *s, uint64_t now) {
    if (now < s->now) return SYSTEM_SLEEP_INVALID_TIME;
    s->now = now;
    if (s->phase == SYSTEM_SLEEP_STARTING && now >= s->startup_until)
        s->phase = SYSTEM_SLEEP_WAKE_DELAY;
    if (s->phase == SYSTEM_SLEEP_WAKE_DELAY && now >= s->ready_at) {
        s->phase = SYSTEM_SLEEP_RUNNING;
        return SYSTEM_SLEEP_WAKE_READY;
    }
    return SYSTEM_SLEEP_NO_CHANGE;
}

uint64_t system_sleep_next_event(const system_sleep_t *s) {
    if (s->phase == SYSTEM_SLEEP_STARTING) return s->startup_until;
    if (s->phase == SYSTEM_SLEEP_WAKE_DELAY) return s->ready_at;
    return UINT64_MAX;
}

uint8_t system_sleep_domains(const system_sleep_t *s, uint8_t prr, int wdt_enabled) {
    uint8_t clocks = SYSTEM_CLOCK_ASYNC;
    if (wdt_enabled) clocks |= SYSTEM_CLOCK_WDT;
    if (s->phase == SYSTEM_SLEEP_RUNNING || s->phase == SYSTEM_SLEEP_WAKE_DELAY)
        clocks |= SYSTEM_CLOCK_CPU | SYSTEM_CLOCK_FLASH | SYSTEM_CLOCK_IO |
                  SYSTEM_CLOCK_ADC | SYSTEM_CLOCK_MAIN;
    else if (s->mode == SYSTEM_SLEEP_IDLE)
        clocks |= SYSTEM_CLOCK_IO | SYSTEM_CLOCK_ADC | SYSTEM_CLOCK_MAIN;
    else if (s->mode == SYSTEM_SLEEP_ADC_NOISE)
        clocks |= SYSTEM_CLOCK_ADC | SYSTEM_CLOCK_MAIN;
    if (clocks & SYSTEM_CLOCK_IO) clocks |= SYSTEM_CLOCK_TIMER0;
    if (prr & 1) clocks &= (uint8_t)~SYSTEM_CLOCK_ADC;
    if (prr & 2) clocks &= (uint8_t)~SYSTEM_CLOCK_TIMER0;
    return clocks;
}

int system_sleep_input_clamp(const system_sleep_t *s) {
    return s->mode == SYSTEM_SLEEP_POWER_DOWN &&
           (s->phase == SYSTEM_SLEEP_ASLEEP || s->phase == SYSTEM_SLEEP_STARTING);
}

int system_sleep_adc_start(const system_sleep_t *s) {
    return s->phase == SYSTEM_SLEEP_ASLEEP &&
           (s->mode == SYSTEM_SLEEP_IDLE || s->mode == SYSTEM_SLEEP_ADC_NOISE);
}
