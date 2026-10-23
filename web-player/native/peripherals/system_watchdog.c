#include "system_watchdog.h"

enum { WDP_MASK = 0x27 };

static void force_control(system_watchdog_t *w) {
    if (w->mcusr & SYSTEM_WDRF) w->control |= SYSTEM_WDE;
    if (w->always_on) {
        w->control |= SYSTEM_WDE;
        w->control &= (uint8_t)~SYSTEM_WDTIE;
    }
}

static int cpu_time(system_watchdog_t *w, uint64_t at) {
    if (at < w->cpu_cycle) return 0;
    w->cpu_cycle = at;
    if ((w->control & SYSTEM_WDCE) && at >= w->unlock_until)
        w->control &= (uint8_t)~SYSTEM_WDCE;
    return 1;
}

void system_watchdog_init(system_watchdog_t *w, int always_on) {
    *w = (system_watchdog_t){0};
    w->always_on = !!always_on;
    system_watchdog_reset(w, SYSTEM_PORF, 0, 0);
}

void system_watchdog_reset(system_watchdog_t *w, uint8_t sources,
                           uint64_t cpu_cycle, uint64_t oscillator_tick) {
    uint8_t flags = (sources & SYSTEM_PORF) ? 0 : w->mcusr;
    w->mcusr = flags | (sources & 15);
    w->control = 0;
    w->counter = 0;
    w->combined_pending = 0;
    w->reset_requested = 0;
    w->unlock_until = 0;
    w->oscillator_tick = oscillator_tick;
    w->cpu_cycle = cpu_cycle;
    w->last_event_tick = oscillator_tick;
    force_control(w);
}

uint32_t system_watchdog_period(const system_watchdog_t *w) {
    uint8_t select = (w->control & 7) | ((w->control >> 2) & 8);
    return select < 10 ? ((uint32_t)2048 << select) : 0;
}

uint32_t system_watchdog_until_timeout(const system_watchdog_t *w) {
    if (w->reset_requested || !(w->control & (SYSTEM_WDE | SYSTEM_WDTIE))) return 0;
    uint32_t period = system_watchdog_period(w);
    if (!period) return 0;
    return w->counter >= period ? 1 : period - w->counter;
}

uint8_t system_watchdog_advance(system_watchdog_t *w, uint64_t cpu_cycle,
                                uint64_t target) {
    if (target < w->oscillator_tick || !cpu_time(w, cpu_cycle))
        return SYSTEM_WDT_TIME_REVERSED;
    if (w->reset_requested) return SYSTEM_WDT_RESET;
    if (!(w->control & (SYSTEM_WDE | SYSTEM_WDTIE))) {
        w->oscillator_tick = target;
        return SYSTEM_WDT_NONE;
    }
    uint32_t period = system_watchdog_period(w);
    if (!period) return SYSTEM_WDT_RESERVED;
    uint8_t events = SYSTEM_WDT_NONE;
    uint64_t elapsed = target - w->oscillator_tick;
    uint32_t left = w->counter >= period ? 1 : period - w->counter;
    if (elapsed < left) {
        w->counter += (uint32_t)elapsed;
        w->oscillator_tick = target;
        return events;
    }
    w->oscillator_tick += left;
    w->counter = 0;
    w->last_event_tick = w->oscillator_tick;
    if (!(w->control & SYSTEM_WDTIE) ||
        ((w->control & SYSTEM_WDE) && w->combined_pending)) {
        w->reset_requested = 1;
        return SYSTEM_WDT_RESET;
    }
    w->control |= SYSTEM_WDTIF;
    events |= SYSTEM_WDT_INTERRUPT;
    if (w->control & SYSTEM_WDE) {
        w->combined_pending = 1;
        elapsed = target - w->oscillator_tick;
        if (elapsed >= period) {
            w->oscillator_tick += period;
            w->last_event_tick = w->oscillator_tick;
            w->reset_requested = 1;
            return events | SYSTEM_WDT_RESET;
        }
    }
    elapsed = target - w->oscillator_tick;
    /* Repeated interrupt-only timeouts coalesce in WDTIF; no callbacks. */
    if (elapsed >= period) w->last_event_tick += (elapsed / period) * period;
    w->counter = (uint32_t)(elapsed % period);
    w->oscillator_tick = target;
    return events;
}

int system_watchdog_read(system_watchdog_t *w, uint8_t io,
                         uint64_t cpu_cycle, uint8_t *value) {
    if (io != SYSTEM_WDTCR && io != SYSTEM_MCUSR) return 0;
    if (!cpu_time(w, cpu_cycle)) return -1;
    *value = io == SYSTEM_WDTCR ? w->control : w->mcusr;
    return 1;
}

int system_watchdog_write(system_watchdog_t *w, uint8_t io, uint8_t value,
                          uint8_t mask, uint64_t cpu_cycle) {
    if (io != SYSTEM_WDTCR && io != SYSTEM_MCUSR) return 0;
    if (!cpu_time(w, cpu_cycle)) return -1;
    if (io == SYSTEM_MCUSR) {
        w->mcusr &= (value | (uint8_t)~mask) & 15;
        force_control(w);
        return 1;
    }
    uint8_t old = w->control;
    uint8_t merged = (old & (uint8_t)~mask) | (value & mask);
    int open = !!(old & SYSTEM_WDCE);
    uint8_t control = old;
    control &= (uint8_t)~(value & mask & SYSTEM_WDTIF);
    control = (control & (uint8_t)~SYSTEM_WDTIE) | (merged & SYSTEM_WDTIE);
    /* WDE can always be set; only the timed sequence permits clearing it or
     * changing WDP. Opening the sequence does not itself change the divisor. */
    control |= merged & SYSTEM_WDE;
    if (open) control = (control & (uint8_t)~(WDP_MASK | SYSTEM_WDE)) |
                        (merged & (WDP_MASK | SYSTEM_WDE));
    if ((value & mask & (SYSTEM_WDCE | SYSTEM_WDE)) == (SYSTEM_WDCE | SYSTEM_WDE)) {
        control |= SYSTEM_WDCE;
        w->unlock_until = cpu_cycle + 4;
    } else if (open && (mask & SYSTEM_WDCE) && !(value & SYSTEM_WDCE)) {
        control &= (uint8_t)~SYSTEM_WDCE;
    }
    w->control = control;
    force_control(w);
    if (!(w->control & SYSTEM_WDE)) w->combined_pending = 0;
    if (!(w->control & (SYSTEM_WDE | SYSTEM_WDTIE))) w->counter = 0;
    return 1;
}

void system_watchdog_wdr(system_watchdog_t *w) {
    w->counter = 0;
}

int system_watchdog_pending(const system_watchdog_t *w) {
    return (w->control & (SYSTEM_WDTIF | SYSTEM_WDTIE)) ==
           (SYSTEM_WDTIF | SYSTEM_WDTIE);
}

void system_watchdog_ack(system_watchdog_t *w) {
    w->control &= (uint8_t)~SYSTEM_WDTIF;
    if (w->control & SYSTEM_WDE) w->control &= (uint8_t)~SYSTEM_WDTIE;
    w->combined_pending = 0;
}
