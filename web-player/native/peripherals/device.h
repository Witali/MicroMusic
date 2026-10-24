#ifndef MICROMUSIC_ATTINY13A_DEVICE_H
#define MICROMUSIC_ATTINY13A_DEVICE_H
#include <stdint.h>
#include "../devices/attiny13a/clki_input.h"

/* One allocation-free board per WASM instance. All I/O addresses are offsets
 * 0..63; caller data-space addresses add 32. No CPU PC/stack/SREG ownership. */
enum {
 DEVICE_CFG_OSCILLATOR_HZ=1, DEVICE_CFG_WATCHDOG_HZ=2,
 DEVICE_CFG_VCC_UV=3, DEVICE_CFG_BANDGAP_UV=4,
 DEVICE_CFG_FUSE_LOW=5, DEVICE_CFG_FUSE_HIGH=6, DEVICE_CFG_LOCK=7,
 DEVICE_CFG_ADC_FIRST_SAMPLE=8, DEVICE_CFG_COMPARATOR_PROPAGATION=9,
 DEVICE_CFG_BANDGAP_STARTUP=10, DEVICE_CFG_COMPARATOR_INITIAL=11,
 DEVICE_CFG_WAKE_STARTUP_BASE_HALF=12, DEVICE_CFG_SPM_COMMAND_CYCLES=13,
 DEVICE_CFG_FLASH_MAXIMUM=14, DEVICE_CFG_BOD_RECOVERY_NS=15,
 DEVICE_CFG_FACTORY_OSCCAL96=16, DEVICE_CFG_FUSE_STARTUP_PROFILE=17,
 DEVICE_CFG_NVM_CLOCK_PROFILE=18, DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ=19
};
enum { DEVICE_NVM_CLOCK_UNSPECIFIED=0, DEVICE_NVM_CLOCK_FIXED_NS=1 };
#define DEVICE_PS_PER_SECOND UINT64_C(1000000000000)
enum { DEVICE_CONTROL_SLEEP=1, DEVICE_CONTROL_SPM=2, DEVICE_CONTROL_WDR=3 };
enum {
 DEVICE_FAULT_CONFIG=1, DEVICE_FAULT_TIME=2, DEVICE_FAULT_TIMER=3,
 DEVICE_FAULT_ANALOG=4, DEVICE_FAULT_NVM=5, DEVICE_FAULT_WATCHDOG=6,
 DEVICE_FAULT_SLEEP=7, DEVICE_FAULT_INPUT_OVERFLOW=8,
 DEVICE_FAULT_OUTPUT_OVERFLOW=9, DEVICE_FAULT_SPM_TIMING=10,
 DEVICE_FAULT_CLKPR=11, DEVICE_FAULT_UNIMPLEMENTED_IO=12,
 DEVICE_FAULT_CLOCK_CONTRACT=13, DEVICE_FAULT_OSCCAL=14,
 DEVICE_FAULT_NVM_CLOCK_PROFILE=15, DEVICE_FAULT_POWER=16,
 DEVICE_FAULT_RESET_INPUT=17, DEVICE_FAULT_CLKI=18
};
enum {
 DEVICE_POWER_ENABLE=0, DEVICE_POWER_POR_ASSERT_UV=1, DEVICE_POWER_POR_RELEASE_UV=2,
 DEVICE_POWER_BOD00_UV=3, DEVICE_POWER_BOD01_UV=4, DEVICE_POWER_BOD10_UV=5,
 DEVICE_POWER_HYSTERESIS_UV=6, DEVICE_POWER_FILTER_NS=7,
 DEVICE_POWER_RECOVERY_NS=8, DEVICE_POWER_FLASH_PROGRAM_MIN_UV=9
};
typedef struct {
 union { uint64_t base_half; uint64_t time_ps; };
 uint8_t levels, driven, pullups, floating, contention;
 uint8_t reserved[3];
} device_pin_event_t;
/* Same wire layout; select the accessor to select the time contract. */
typedef device_pin_event_t device_pin_event_ps_t;

/* Configure BEFORE init. Defaults: 9.6MHz oscillator, nominal128kHz watchdog,
 * 5V supply/1.1V bandgap, fuses7a/ff, lockff, ADC first sample27 half ADC
 * periods, comparator propagation0/startup0/initial0, wake startup0,
 * SPM command cycles0 (explicit fault if needed), Flash maximum bound,
 * BOD recovery60000ns (datasheet approximate digital profile, configurable),
 * factory OSCCAL96=0 (explicit fixture byte, not a universal chip value),
 * fuse startup profile0 (zero-delay digital fixture; set1 for fuse timing).
 * DWEN must be unprogrammed for every clock/reset profile. Until debugWIRE
 * startup, PB5 mux and sleep-clock behavior are implemented, init rejects
 * programmed DWEN with DEVICE_FAULT_CONFIG/detail14, regardless of lock bits
 * or RSTDISBL. The host diagnostic BREAK option does not emulate debugWIRE. */
int device_configure(uint32_t key, uint32_t value);
/* Opt-in physical1ps supply profile. field0 enables; all fields1..9 must be
 * explicitly provided before init. field0=0 clears the profile selection.
 * Thresholds are selected digital-profile microvolts, timings nanoseconds;
 * no typical threshold is silently assumed for a physical chip. Requires an
 * explicit physical source: an OSCCAL table or the CLKI profile. */
int device_configure_power(uint32_t field, uint32_t value);
uint8_t device_power_enabled(void);
int32_t device_vcc_microvolts(void);
enum {
 DEVICE_RESET_INPUT_ENABLE=0, DEVICE_RESET_INPUT_ASSERT_PPM=1,
 DEVICE_RESET_INPUT_RELEASE_PPM=2, DEVICE_RESET_INPUT_ASSERT_QUALIFICATION_NS=3,
 DEVICE_RESET_INPUT_RELEASE_QUALIFICATION_NS=4,
 DEVICE_RESET_INPUT_ASSERT_PROPAGATION_NS=5, DEVICE_RESET_INPUT_RELEASE_PROPAGATION_NS=6
};
/* Optional analog PB5 RESET receiver. Configure all six explicit parameters
 * before enabling, in physical1ps mode with DWEN unprogrammed. Analog PB5 is
 * selected with inject_analog_ps; before that its voltage follows VCC.
 * Prequalified digital PB5 reset remains an independent bypass input.
 * RSTDISBL gates the RESET role; the receiver itself retains diagnostic state. */
int device_configure_reset_input(uint32_t field,uint32_t value);
uint8_t device_reset_input_enabled(void);
uint8_t device_reset_input_asserted(void);
uint64_t device_reset_input_deadline_ps(void);
/* Explicit digital CLKI fixture: field0 enables, field1 supplies initial PB3
 * level; field2 selects optional datasheet-ideal-v1 validation. CKSEL00 and
 * bounded CPU continuation are required by the host API.
 * Physical1ps time does not require an unrelated internal RC calibration. */
int device_configure_clki(uint32_t field,uint32_t value);
uint8_t device_clki_enabled(void);
uint8_t device_clki_validation_enabled(void);
int device_clki_enqueue(const attiny13a_clki_edge_t *edges,uint32_t count,uint64_t known_until_ps);
/* Finite exact periodic producer, lazily refilling the same edge queue in C.
 * Start is at/after the old horizon; initial level must match the queued tail.
 * No period is inferred from measurements and no edge exists beyond count. */
int device_clki_periodic_ps(uint64_t start_ps,uint32_t initial_level,uint64_t high_ps,
 uint64_t low_ps,uint64_t edge_count,uint64_t known_until_ps);
uint64_t device_clki_periodic_remaining(void);
uint64_t device_clki_horizon_ps(void);
uint32_t device_clki_count(void);
uint32_t device_clki_free(void);
uint8_t device_clki_level(void);
/* COMPLETE0, WAIT_CLOCK1 (known held interval), WAIT_INPUT2 (unknown future). */
uint8_t device_clki_status(void);
uint8_t device_clki_aligned(void);
uint64_t device_clki_startup_ck(void);
/* Pre-init, instance-specific CAL[0..127] -> internal RC Hz table. Zero means
 * unknown. Calling this opts into fixed1ps time. A factory entry is required;
 * for an internal RC source it must match configured oscillatorHz. No curve is
 * interpolated. clear restores the legacy fixed-frequency timing contract. */
int device_configure_osccal_hz(uint32_t cal, uint32_t hz);
void device_clear_osccal_hz(void);
uint8_t device_physical_mode(void);
int device_init(uint8_t data[160], uint8_t flash[1024], uint8_t eeprom[64]);
void device_reset(uint8_t reset_sources);
uint8_t device_read(uint8_t io);
/* maskff=OUT/ST, one bit=SBI/CBI. Returns additional NVM CPU stall cycles. */
uint32_t device_write(uint8_t io, uint8_t value, uint8_t mask);
void device_advance(uint32_t cpu_cycles);
/* CPU bus sampling can precede its final rising edge by half a CPU cycle. */
void device_advance_half(uint64_t cpu_half_cycles);
/* Opt-in physical-time CPU continuation span. Consume at most wanted virtual
 * CPU half periods and never pass wall_deadline_ps (UINT64_MAX means no wall
 * bound). Retain the fractional clock phase across WAIT, including CLKPR
 * transitions. *consumed is the actual whole-half delta, never a rounded-up
 * budget. Return1 COMPLETE,0 WAIT/reset hold/startup, or-1 fault/reset request.
 * A zero span flushes current events and can retire during BOD wake recovery;
 * reset/fault still wins. A nonzero span waits for recovery completion.
 * The caller owns remaining instruction work and must cancel it on reset. */
int device_advance_half_until_ps(uint64_t wanted,uint64_t wall_deadline_ps,
                                 uint64_t *consumed);
/* In CLKI mode, same continuation contract plus return2 BUFFER_READY when a
 * PCM or legacy audio-owned host ring is half full. The native consumer drains
 * these queues and retries
 * the remaining phase before returning to generated code. Fixed internal
 * sources retain the ordinary bounded advance. No effect is repeated. */
int device_advance_half_until_ps_buffered(uint64_t wanted,uint64_t wall_deadline_ps,
                                          uint64_t *consumed);
/* advance stops at an asynchronous reset deadline even inside an instruction;
 * the CPU bridge must abandon its remaining bus/register effects and reset. */
/* Conservative nominal CPU-cycle distance, rounded DOWN. A block must end
 * strictly before this bound, including physical-picosecond endpoint ties.
 * UINT64_MAX means no event. IRQ requests are queried apart. */
uint64_t device_next_cpu_event(void);
uint64_t device_base_half(void);
uint64_t device_virtual_half(void);
/* Fixed1ps APIs require the explicit OSCCAL table or CLKI profile. Legacy timed
 * APIs (including pin getters) fail CLOCK_CONTRACT in this mode, preserving
 * their original initial-half-oscillator-period meaning. CPU-cycle APIs,
 * GPIO/analog register APIs and ring consume remain common to both modes. */
uint64_t device_time_ps(void);
uint64_t device_wait_until_ps(uint64_t deadline_ps);
/* Native streaming consumer variant. May yield early when a PCM or legacy
 * audio-owned host ring is half full, so C/WASM can drain it before continuing
 * the same wall deadline. Explicitly retained host history is never a yield
 * condition: its owner must drain it, otherwise append reports overflow.
 * This neither consumes pins nor invokes a JavaScript callback. */
uint64_t device_wait_until_ps_buffered(uint64_t deadline_ps);
uint64_t device_startup_deadline_ps(void);
uint64_t device_cpu_half_deadline_ps(uint64_t cpu_half_cycles);
/* Rounded-UP relative CPU half-cycle budget to a physical deadline. The
 * caller must recompute after clock writes; an instruction may straddle it. */
uint64_t device_cpu_halves_until_ps(uint64_t deadline_ps);
/* start+floor(frame*1e12/rate), independent of oscillator and CLKPR. */
uint64_t device_next_sample_ps(uint64_t start_ps,uint64_t frame,uint32_t rate);
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
/* Without a power profile these are logical BODCR observers. With an explicit
 * power profile they also reflect the supply observer's sleep/recovery state. */
uint8_t device_bod_disabled(void);
uint8_t device_bod_recovering(void);
const device_pin_event_t *device_pin_state(void);
/* Advance halted hardware to wake/program completion or caller deadline;
 * returns elapsed complete virtual CPU periods, including clock-stopped spans.
 * Board time remains authoritative if the endpoint is between CPU edges. */
uint64_t device_wait_until(uint64_t base_half_deadline);
uint8_t device_reset_requested(void);
/* Ideal digital RESET input: PB5 low means an ALREADY RECOGNIZED assertion,
 * bypassing an analog pulse filter. RSTDISBL disables this RESET role.
 * device_reset acknowledges the request, but halted remains true until queued
 * PB5 high/release. An enabled supply profile additionally aggregates POR/BOD
 * and the WDT pulse. Optional fuse startup begins after the final release.
 * Power-profile peripherals reset at ASSERT; device_reset acknowledges the
 * CPU request without reinitializing the observer or resetting them twice. */
uint8_t device_reset_held(void);
/* Optional fuse reset stretch, independent of a physical RESET hold. The
 * deadline uses base_half; UINT64_MAX means external RESET is still held,
 * and current base_half means no reset stretch remains. */
uint8_t device_starting(void);
uint64_t device_startup_deadline(void);
uint64_t device_flash_generation(void);
uint32_t device_take_dirty_pages(void);
uint32_t device_fault(void);
uint32_t device_fault_detail(void);
/* Queue chronological injections, timestamped in HALF oscillator periods,
 * independent CLKPR. Equal-time inputs apply AFTER device sampling. */
int device_inject_digital(uint64_t base_half, uint8_t driven_mask, uint8_t levels);
int device_inject_analog(uint64_t base_half, uint8_t pb_pin, int32_t microvolts);
int device_inject_digital_ps(uint64_t time_ps, uint8_t driven_mask, uint8_t levels);
int device_inject_analog_ps(uint64_t time_ps, uint8_t pb_pin, int32_t microvolts);
/* VCC0 is valid for an enabled profile. Inputs use the shared ordered queue. */
int device_inject_vcc_ps(uint64_t time_ps, int32_t microvolts);
const device_pin_event_t *device_pin_events(uint32_t *count);
const device_pin_event_ps_t *device_pin_events_ps(uint32_t *count);
const device_pin_event_ps_t *device_pin_state_ps(void);
void device_consume_pin_events(uint32_t count);
uint64_t device_dropped_pin_events(void);
void device_clear_pin_events(void);
/* Host observation, independent of live GPIO and the native PCM consumer.
 * Post-init mask0..63 selects changes in all five pin metadata bytes; retain
 * selects explicit ownership during audio. Default63/0 preserves legacy audio
 * auto-discard. Changes retain queued rows and create no synthetic snapshot;
 * read device_pin_state[_ps] for the current unmasked baseline. MCU reset
 * preserves subscriptions/history; cold init restores defaults. Invalid
 * requests return0 without changing state. Getter packs mask|(retain<<8). */
int device_configure_pin_trace(uint32_t mask,uint32_t retain_during_audio);
uint32_t device_pin_trace_configuration(void);
/* Internal native-audio subscription. Valid masks0/2/3 mean off/PB1/PB0+PB1.
 * Starting a new audio timeline clears only its own queue, with no fake initial
 * event. Capture initial live levels separately. PCM records level changes;
 * host consume/clear never consumes them. Both time contracts use the same
 * event layout. A configured subscription persists between capture calls and
 * across MCU reset; its bounded backlog faults on overflow. */
int device_configure_audio_pins(uint8_t mask);
const device_pin_event_t *device_audio_pin_events(uint32_t *count);
void device_consume_audio_pin_events(uint32_t count);
/* Preserve the former audio-owned host-history discard only for retain0. */
void device_discard_audio_trace(uint64_t until);
/* Native audio pressure query over TOTAL queue occupancy, including wrap.
 * Ready at512 rows in PCM or legacy auto-discard host history. Explicitly
 * retained host history is the host consumer's responsibility. No mutation. */
int device_pin_buffer_ready(void);
#endif
