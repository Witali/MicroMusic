#ifndef MICROMUSIC_ATTINY13A_DEVICE_H
#define MICROMUSIC_ATTINY13A_DEVICE_H
#include <stdint.h>

/* One allocation-free board per WASM instance. All I/O addresses are offsets
 * 0..63; caller data-space addresses add 32. No CPU PC/stack/SREG ownership. */
enum {
 DEVICE_CFG_OSCILLATOR_HZ=1, DEVICE_CFG_WATCHDOG_HZ=2,
 DEVICE_CFG_VCC_UV=3, DEVICE_CFG_BANDGAP_UV=4,
 DEVICE_CFG_FUSE_LOW=5, DEVICE_CFG_FUSE_HIGH=6, DEVICE_CFG_LOCK=7,
 DEVICE_CFG_ADC_FIRST_SAMPLE=8, DEVICE_CFG_COMPARATOR_PROPAGATION=9,
 DEVICE_CFG_BANDGAP_STARTUP=10, DEVICE_CFG_COMPARATOR_INITIAL=11,
 DEVICE_CFG_WAKE_STARTUP_BASE_HALF=12, DEVICE_CFG_SPM_COMMAND_CYCLES=13,
 DEVICE_CFG_FLASH_MAXIMUM=14
};
enum { DEVICE_CONTROL_SLEEP=1, DEVICE_CONTROL_SPM=2, DEVICE_CONTROL_WDR=3 };
enum {
 DEVICE_FAULT_CONFIG=1, DEVICE_FAULT_TIME=2, DEVICE_FAULT_TIMER=3,
 DEVICE_FAULT_ANALOG=4, DEVICE_FAULT_NVM=5, DEVICE_FAULT_WATCHDOG=6,
 DEVICE_FAULT_SLEEP=7, DEVICE_FAULT_INPUT_OVERFLOW=8,
 DEVICE_FAULT_OUTPUT_OVERFLOW=9, DEVICE_FAULT_SPM_TIMING=10,
 DEVICE_FAULT_CLKPR=11, DEVICE_FAULT_UNIMPLEMENTED_IO=12
};
typedef struct {
 uint64_t base_half;
 uint8_t levels, driven, pullups, floating, contention;
 uint8_t reserved[3];
} device_pin_event_t;

/* Configure BEFORE init. Defaults: 9.6MHz oscillator, nominal128kHz watchdog,
 * 5V supply/1.1V bandgap, fuses7a/ff, lockff, ADC first sample27 half ADC
 * periods, comparator propagation0/startup0/initial0, wake startup0,
 * SPM command cycles0 (explicit fault if needed), Flash maximum bound. */
int device_configure(uint32_t key, uint32_t value);
int device_init(uint8_t data[160], uint8_t flash[1024], uint8_t eeprom[64]);
void device_reset(uint8_t reset_sources);
uint8_t device_read(uint8_t io);
/* maskff=OUT/ST, one bit=SBI/CBI. Returns additional NVM CPU stall cycles. */
uint32_t device_write(uint8_t io, uint8_t value, uint8_t mask);
void device_advance(uint32_t cpu_cycles);
/* CPU bus sampling can precede its final rising edge by half a CPU cycle. */
void device_advance_half(uint64_t cpu_half_cycles);
/* advance stops at an asynchronous reset deadline even inside an instruction;
 * the CPU bridge must abandon its remaining bus/register effects and reset. */
/* Safe distance in nominal CPU cycles, rounded UP to include an event inside
 * an instruction. UINT64_MAX means no event. IRQ requests are queried apart. */
uint64_t device_next_cpu_event(void);
uint64_t device_base_half(void);
uint64_t device_virtual_half(void);
/* Actual waveform divisor. A protected CLKPR request takes one old period
 * followed by one new period to establish its two transition edges (the
 * deterministic T1+T2 lower bound in DS40002307A6.3.1). */
uint32_t device_clkpr_divisor(void);
uint32_t device_oscillator_hz(void);
uint16_t device_pending_irqs(void); /* bit N means vector word N */
uint8_t device_next_irq(void);     /* lowest vector word, or0 */
void device_ack_irq(uint8_t vector_word);
/* SLEEP/WDR called AFTER the CPU charges their1 cycle. SPM called at its
 * instruction-effect edge; returned cycles are command cycles to charge.
 * Page-program wall latency is consumed only by wait_until, never twice. */
uint32_t device_control(uint8_t command, uint16_t z, uint16_t r1r0);
uint8_t device_lpm(uint16_t z);
int device_halted(void);
uint8_t device_sleep_phase(void);
const device_pin_event_t *device_pin_state(void);
/* Advance halted hardware to wake/program completion or caller deadline;
 * returns elapsed complete virtual CPU periods, including clock-stopped spans.
 * Board time remains authoritative if the endpoint is between CPU edges. */
uint64_t device_wait_until(uint64_t base_half_deadline);
uint8_t device_reset_requested(void);
/* Ideal digital RESET profile: PB5 low means an ALREADY RECOGNIZED assertion,
 * bypassing an analog pulse filter. RSTDISBL disables this RESET role.
 * device_reset acknowledges the request, but halted remains true until queued
 * PB5 high/release. No automatic fuse/startup delay is invented on release. */
uint8_t device_reset_held(void);
uint64_t device_flash_generation(void);
uint32_t device_take_dirty_pages(void);
uint32_t device_fault(void);
uint32_t device_fault_detail(void);
/* Queue chronological injections, timestamped in HALF oscillator periods,
 * independent CLKPR. Equal-time inputs apply AFTER device sampling. */
int device_inject_digital(uint64_t base_half, uint8_t driven_mask, uint8_t levels);
int device_inject_analog(uint64_t base_half, uint8_t pb_pin, int32_t microvolts);
const device_pin_event_t *device_pin_events(uint32_t *count);
void device_consume_pin_events(uint32_t count);
uint64_t device_dropped_pin_events(void);
void device_clear_pin_events(void);
#endif
