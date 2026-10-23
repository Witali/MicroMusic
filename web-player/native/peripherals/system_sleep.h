#ifndef MICROMUSIC_TINY13_SYSTEM_SLEEP_H
#define MICROMUSIC_TINY13_SYSTEM_SLEEP_H

#include <stdint.h>
#include "../attiny13a-registers.h"

enum {
    SYSTEM_SLEEP_IDLE = AT13_SLEEP_MODE_IDLE >> AT13_BIT_SM0,
    SYSTEM_SLEEP_ADC_NOISE = AT13_SLEEP_MODE_ADC >> AT13_BIT_SM0,
    SYSTEM_SLEEP_POWER_DOWN = AT13_SLEEP_MODE_PWR_DOWN >> AT13_BIT_SM0,
    SYSTEM_SLEEP_RUNNING = 0, SYSTEM_SLEEP_ASLEEP = 1,
    SYSTEM_SLEEP_STARTING = 2, SYSTEM_SLEEP_WAKE_DELAY = 3,
    SYSTEM_SLEEP_NO_CHANGE = 0, SYSTEM_SLEEP_ENTERED = 1,
    SYSTEM_SLEEP_RESERVED = 2, SYSTEM_SLEEP_RESET = 4,
    SYSTEM_SLEEP_WAKE_STARTED = 8, SYSTEM_SLEEP_WAKE_READY = 16,
    SYSTEM_SLEEP_INVALID_TIME = 32, SYSTEM_SLEEP_BUSY = 64,
    SYSTEM_SLEEP_EXTRA_WAKE_CYCLES = 4, SYSTEM_SLEEP_NORMAL_IRQ_CYCLES = 4,
    SYSTEM_CLOCK_CPU = 1, SYSTEM_CLOCK_FLASH = 2, SYSTEM_CLOCK_IO = 4,
    SYSTEM_CLOCK_ADC = 8, SYSTEM_CLOCK_WDT = 16, SYSTEM_CLOCK_ASYNC = 32,
    SYSTEM_CLOCK_MAIN = 64, SYSTEM_CLOCK_TIMER0 = 128,
    /* Bit positions match vector-word addresses; RESET is bit zero. */
    SYSTEM_WAKE_RESET = 1u << AT13_VECTOR_RESET, SYSTEM_WAKE_INT0 = 1u << AT13_VECTOR_INT0,
    SYSTEM_WAKE_PCINT = 1u << AT13_VECTOR_PCINT0, SYSTEM_WAKE_TIMER_OVF = 1u << AT13_VECTOR_TIM0_OVF,
    SYSTEM_WAKE_NVM_READY = 1u << AT13_VECTOR_EE_RDY, SYSTEM_WAKE_COMPARATOR = 1u << AT13_VECTOR_ANA_COMP,
    SYSTEM_WAKE_TIMER_A = 1u << AT13_VECTOR_TIM0_COMPA, SYSTEM_WAKE_TIMER_B = 1u << AT13_VECTOR_TIM0_COMPB,
    SYSTEM_WAKE_WDT = 1u << AT13_VECTOR_WDT, SYSTEM_WAKE_ADC = 1u << AT13_VECTOR_ADC
};

typedef struct {
    /* Uniform scheduler time units, chosen by the board (e.g. half-clocks).
     * startup_ticks includes actual fuse/oscillator/BOD recovery for this wake;
     * it is not guessed from the selected sleep mode or a typical analog time. */
    uint64_t startup_ticks, ticks_per_cpu_cycle;
} system_sleep_timing_t;

typedef struct {
    uint64_t now, sleep_at, wake_at, startup_until, ready_at;
    uint16_t wake_sources;
    uint8_t mode, phase;
} system_sleep_t;

void system_sleep_reset(system_sleep_t *sleep, uint64_t now);
/* MCUCR remains owned by the GPIO/bus module. CPU has already executed SLEEP
 * (PC advance and one instruction cycle) when calling this policy boundary. */
uint8_t system_sleep_enter(system_sleep_t *sleep, uint8_t mcucr, uint64_t now);
uint16_t system_sleep_wake_mask(uint8_t mode, int int0_level_sense);
/* asserted/enabled use SYSTEM_WAKE_* bits. enabled represents individual source
 * masks; reset does not require an enable. CPU owns SREG.I/vector arbitration.
 * Startup cancellation of an INT0 level must be decided from live GPIO at IRQ
 * acceptance; the original wake source is not an instruction to force its ISR. */
uint8_t system_sleep_wake(system_sleep_t *sleep, uint16_t asserted,
                          uint16_t enabled, int int0_level_sense,
                          system_sleep_timing_t timing, uint64_t now);
/* Physical clock schedulers can round the entire four-cycle hold once,
 * without rounding an individual CPU period and then multiplying it. */
uint8_t system_sleep_wake_exact(system_sleep_t *sleep,uint16_t asserted,
 uint16_t enabled,int int0_level_sense,uint64_t startup_ticks,
 uint64_t extra_wake_ticks,uint64_t now);
uint8_t system_sleep_advance(system_sleep_t *sleep, uint64_t now);
uint64_t system_sleep_next_event(const system_sleep_t *sleep);
/* Availability of clock domains. The owning peripheral also applies its enable
 * bits. PRR masks Timer0/ADC. WDT remains independent in every sleep mode. */
uint8_t system_sleep_domains(const system_sleep_t *sleep, uint8_t prr, int wdt_enabled);
int system_sleep_input_clamp(const system_sleep_t *sleep);
/* Idle and ADC Noise Reduction may request an automatic conversion. The analog
 * module must check its own ADEN/ADIE/busy/single-conversion requirements. */
int system_sleep_adc_start(const system_sleep_t *sleep);

#endif
