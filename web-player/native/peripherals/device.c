#include "device.h"
#include "../attiny13a-registers.h"
#include "timer0.h"
#include "system_gpio.h"
#include "system_sleep.h"
#include "system_watchdog.h"
#include "analog.h"
#include "nvm.h"
#include "device_clock.h"
#include "power_reset.h"
#include "../devices/attiny13a/reset_input.h"
#include <stddef.h>

enum { PIN_CAPACITY=1024, INPUT_CAPACITY=128,
 CLKPR=AT13_IO_CLKPR, OSCCAL=AT13_IO_OSCCAL, BODCR=AT13_IO_BODCR };
typedef struct {
 uint64_t at;
 int32_t voltage;
 uint8_t type, mask, value, pin;
} input_t;
enum deadline_reason {
 DEADLINE_INIT, DEADLINE_ELAPSE, DEADLINE_SERVICE,
 DEADLINE_READ, DEADLINE_WRITE, DEADLINE_IRQ_ACK,
 DEADLINE_CONTROL, DEADLINE_LPM, DEADLINE_INPUT,
 DEADLINE_RESET, DEADLINE_FAULT
};
typedef struct {
 uint8_t *data, *flash, *eeprom;
 uint32_t config[20], calibration[128], oscillator_hz;
 uint64_t base, half, phase, ns, ns_remainder, wdt_ticks, wdt_remainder;
 uint64_t clkpr_until, clkpr_switch_half, dropped;
 uint64_t bod_arm_until, bod_sleep_until, bod_recovery_until;
 uint64_t reset_until;
 uint32_t fault, detail, divisor, pending_divisor;
 uint16_t input_head, input_count, pin_head, pin_count;
 uint8_t initialized, clkpr, prr, domains, reset_requested, reset_held, analog_mask;
 uint8_t external_mask, external_levels;
 uint8_t bodcr, bod_armed, bod_committed, bod_disabled;
 uint8_t physical;
 uint8_t power_enabled, reset_preapplied, raw_other_reset;
 uint32_t power_config[10];
 int32_t vcc_uv;
 uint64_t wdt_reset_end;
 struct { uint64_t base, at; uint8_t valid; } deadline;
 power_reset_t power;
 attiny13a_reset_input_t reset_input;
 uint32_t reset_input_config[7];
 uint8_t reset_input_enabled;
 int32_t analog_uv[6];
 timer0_t timer;
 system_gpio_t gpio;
 analog_t analog;
 system_watchdog_t watchdog;
 system_sleep_t sleep;
 attiny13a_nvm_t nvm;
 device_pin_event_t pins;
 device_pin_event_t pin_events[PIN_CAPACITY];
 input_t inputs[INPUT_CAPACITY];
} device_t;
static device_t board;
static uint32_t configuration[20] = {
 0,9600000,128000,5000000,1100000,0x7a,0xff,0xff,27,0,0,0,0,0,1,60000,0,0,0,0
};
static uint32_t calibration_configuration[128];
static uint8_t calibration_configured;
static uint32_t power_configuration[10];
static uint16_t power_fields;
static uint32_t reset_input_configuration[7];
static uint8_t reset_input_fields;
static void reset_state(uint8_t sources_mask);
static void clock_domains(void);
static void mirror(void);

/* Reuse only an unchanged, same-base serviced state. An absolute deadline is
 * not assumed invariant across any clock advance, including a zero delta. */
static inline void deadline_invalidate(enum deadline_reason reason) {
 (void)reason;
 board.deadline.valid=0;
}
static uint64_t minimum(uint64_t a, uint64_t b) { return a < b ? a : b; }
static void fail(uint32_t fault, uint32_t detail) {
 deadline_invalidate(DEADLINE_FAULT);
 if (!board.fault) { board.fault=fault; board.detail=detail; }
}
static uint64_t add(uint64_t a, uint64_t b) {
 if (b > UINT64_MAX-a) { fail(DEVICE_FAULT_TIME,1); return UINT64_MAX; }
 return a+b;
}
static uint64_t multiply(uint64_t a, uint64_t b) {
 if (b && a > UINT64_MAX/b) { fail(DEVICE_FAULT_TIME,2); return UINT64_MAX; }
 return a*b;
}
static uint64_t cpu_cycle(void) { return board.half/2; }
static uint64_t base_frequency(void) {
 return board.physical ? DEVICE_PS_PER_SECOND : (uint64_t)board.config[1]*2;
}
static uint64_t source_rate(void) { return (uint64_t)board.oscillator_hz*2; }
static int time_contract(int physical,uint32_t operation) {
 if (board.physical==physical) return 1;
 fail(DEVICE_FAULT_CLOCK_CONTRACT,operation); return 0;
}
static uint64_t ratio(uint64_t value,uint64_t rate,uint64_t carry,uint64_t denominator,
 uint64_t *remainder) {
 uint64_t result;
 if (!device_clock_ratio(value,rate,carry,denominator,&result,remainder)) {
  fail(DEVICE_FAULT_TIME,11); return UINT64_MAX;
 }
 return result;
}
static uint64_t duration(uint64_t units,uint64_t denominator,uint64_t rate,uint64_t phase) {
 uint64_t ticks;
 if (!device_clock_delay(units,denominator,rate,phase,&ticks)) {
  fail(DEVICE_FAULT_TIME,12); return UINT64_MAX;
 }
 return ticks;
}
static uint64_t source_duration(uint64_t halves) {
 return duration(halves,base_frequency(),source_rate(),0);
}
static void bod_expire(void) {
 uint64_t now=cpu_cycle();
 if (board.bod_sleep_until && now>=board.bod_sleep_until) {
  board.bodcr&=(uint8_t)~2; board.bod_sleep_until=0; board.bod_committed=0;
 }
 if (board.bod_arm_until && now>=board.bod_arm_until) {
  board.bodcr&=(uint8_t)~1; board.bod_arm_until=0; board.bod_armed=0;
 }
}
static void bod_write(uint8_t value) {
 bod_expire();
 uint64_t now=cpu_cycle();
 value&=3;
 if (value&1) {
  /* The specified first write sets BOTH bits; BODSE alone does not arm BODS. */
  board.bodcr=(uint8_t)((board.bodcr&value&2)|1);
  board.bod_arm_until=add(now,4); board.bod_armed=(value&2)!=0;
  board.bod_committed=0;
  if (value&2) { board.bodcr|=2; board.bod_sleep_until=add(now,3); }
  else board.bod_sleep_until=0;
 } else {
  if ((value&2) && board.bod_armed && (board.bodcr&1) && now<board.bod_arm_until) {
   board.bodcr=2; board.bod_sleep_until=add(now,3); board.bod_committed=1;
  } else {
   board.bodcr&=value&2;
   if (!(board.bodcr&2)) { board.bod_sleep_until=0; board.bod_committed=0; }
  }
  board.bod_arm_until=0; board.bod_armed=0;
 }
}
static int external_reset_asserted(void) {
 return (board.config[DEVICE_CFG_FUSE_HIGH]&AT13_FUSE_HIGH_RSTDISBL_MASK) &&
  (((board.external_mask&32) && !(board.external_levels&32)) ||
   (board.reset_input_enabled&&attiny13a_reset_input_asserted(&board.reset_input)));
}
/* Convert elapsed base ticks with retained numerator phase, without ever
 * multiplying a long absolute timestamp by a frequency. */
static uint64_t rational(uint64_t delta, uint64_t rate, uint64_t *remainder) {
 return ratio(delta,rate,*remainder,base_frequency(),remainder);
}
static uint64_t after_units(uint64_t units, uint64_t rate, uint64_t remainder) {
 if (!units) return board.base;
 return add(board.base,duration(units,base_frequency(),rate,remainder));
}
static int reset_starting(void) { return board.base<board.reset_until; }
static void reset_startup(uint8_t sources) {
 board.reset_until=0;
 if (!board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE] || board.reset_held) return;
 uint8_t low=(uint8_t)board.config[DEVICE_CFG_FUSE_LOW];
 unsigned sut=(low>>2)&3;
 uint32_t pulses=sut==2 ? 8192 : sut==1 ? 512 : 0;
 /* Internal source tables6-5/6-6 require the4ms reset minimum with RSTDISBL.
  * The external clock table6-3 has no such footnote. */
 if (!sut && (low&3) && !(board.config[DEVICE_CFG_FUSE_HIGH]&1)) pulses=512;
 uint64_t pulse=!board.power_enabled&&(sources&SYSTEM_WDRF) ? source_duration(2) : 0;
 uint64_t at=add(board.base,pulse);
 if (pulses) {
  uint64_t rate=board.config[DEVICE_CFG_WATCHDOG_HZ];
  uint64_t phase;
  ratio(pulse,rate,board.wdt_remainder,base_frequency(),&phase);
  at=add(at,duration(pulses,base_frequency(),rate,phase));
 }
 /* Explicit digital order: one-CK WDT reset pulse, asynchronous timeout,
  * then6CK oscillator startup plus14CK additional reset delay. CK is the
  * configured undivided source period, never a CLKPR CPU period. */
 board.reset_until=add(at,source_duration(40));
}
static int power_recovering(void) {
 return board.power_enabled && board.power.recovery_deadline!=POWER_RESET_NEVER;
}
static void supply_guard(void) {
 uint32_t mask=0;
 /* The EEPROM erratum also applies to a known constant supply. A dynamic
  * POR/BOD profile is only needed for voltage changes, not this1.9V boundary. */
 if(board.vcc_uv<1900000) mask|=NVM_FAULT_EEPROM_VOLTAGE_UNCERTAIN;
 if(board.power_enabled&&board.vcc_uv<(int32_t)board.power_config[DEVICE_POWER_FLASH_PROGRAM_MIN_UV])
  mask|=NVM_FAULT_FLASH_VOLTAGE_UNCERTAIN;
 nvm_voltage_uncertain(&board.nvm,mask);
 if(board.nvm.faults) fail(DEVICE_FAULT_NVM,board.nvm.faults);
}
static void power_sync(void) {
 power_reset_event_t event;
 board.reset_held=board.power.held;
 while(power_reset_pop_event(&board.power,&event)) {
  if(event.kind==POWER_RESET_ASSERT) {
   board.reset_until=0;reset_state(event.flags_set);
   board.reset_requested|=event.flags_set;board.reset_preapplied=1;
  } else if(event.kind==POWER_RESET_HOLD && event.flags_set) {
   /* Additional reset causes update MCUSR/WDE, without a second CPU restart. */
   system_watchdog_reset(&board.watchdog,event.flags_set,cpu_cycle(),board.wdt_ticks);
  } else if(event.kind==POWER_RESET_RELEASE) reset_startup(event.causes);
 }
 board.reset_held=board.power.held;
 board.bod_disabled=board.power.bod_sleep_off;
 board.bod_recovery_until=power_recovering()?board.power.recovery_deadline:0;
 if(board.power.fault) fail(DEVICE_FAULT_POWER,board.power.fault);
 clock_domains();mirror();
}
static void power_other_sources(void) {
 board.raw_other_reset=(uint8_t)((board.raw_other_reset&POWER_RESET_WDRF)|
  (external_reset_asserted()?POWER_RESET_EXTRF:0));
 power_reset_set_other_sources(&board.power,board.base,board.raw_other_reset);
 power_sync();
}
static void external_reset_sync(void) {
 if(board.power_enabled){power_other_sources();return;}
 uint8_t held=(uint8_t)external_reset_asserted();
 if(held&&!board.reset_held)board.reset_requested|=SYSTEM_EXTRF;
 uint8_t released=board.reset_held&&!held;
 board.reset_held=held;
 if(held)board.reset_until=0;
 else if(released)reset_startup(SYSTEM_EXTRF);
}
static void reset_input_voltage(void) {
 if(!board.reset_input_enabled)return;
 int32_t voltage=(board.analog_mask&32)?board.analog_uv[5]:board.vcc_uv;
 if(!attiny13a_reset_input_set_voltage(&board.reset_input,board.base,voltage,board.vcc_uv))
  fail(DEVICE_FAULT_RESET_INPUT,board.reset_input.fault);
}
static uint64_t at_half(uint64_t half) {
 if (half==UINT64_MAX) return UINT64_MAX;
 if (half<=board.half) return board.base;
 return add(board.base,duration(half-board.half,base_frequency()*board.divisor,
  source_rate(),board.phase));
}
static uint64_t at_cycle(uint64_t cycle) {
 return cycle==UINT64_MAX || cycle>UINT64_MAX/2 ? UINT64_MAX : at_half(cycle*2);
}
static int same_pins(const device_pin_event_t *a, const device_pin_event_t *b) {
 return a->levels==b->levels && a->driven==b->driven && a->pullups==b->pullups &&
  a->floating==b->floating && a->contention==b->contention;
}
static void capture_pins(void) {
 device_pin_event_t pins={{board.base},board.gpio.pins.levels,board.gpio.pins.driven,
  board.gpio.pins.pullups,board.gpio.pins.floating,board.gpio.pins.contention,{0}};
 if (same_pins(&pins,&board.pins)) return;
 board.pins=pins;
 if (board.pin_count) {
  unsigned last=(board.pin_head+board.pin_count-1)%PIN_CAPACITY;
  if (board.pin_events[last].base_half==board.base) { board.pin_events[last]=pins; return; }
 }
 if (board.pin_count==PIN_CAPACITY) {
  if (board.dropped!=UINT64_MAX) ++board.dropped;
  fail(DEVICE_FAULT_OUTPUT_OVERFLOW,PIN_CAPACITY);
  return;
 }
 board.pin_events[(board.pin_head+board.pin_count++)%PIN_CAPACITY]=pins;
}
static void pin_voltages(void) {
 for (unsigned pin=0;pin<6;pin++) {
  int32_t voltage=(board.analog_mask&(1u<<pin)) ? board.analog_uv[pin] :
   ((board.gpio.pins.levels&(1u<<pin)) ? board.vcc_uv : 0);
  /* analog_input advances sampling before mutating the physical voltage. */
  if (!analog_input(&board.analog,(uint8_t)pin,voltage,board.half))
   fail(DEVICE_FAULT_ANALOG,1);
 }
}
static void timer_outputs(void) {
 if (board.gpio.override_mask!=board.timer.overrides ||
     board.gpio.override_levels!=board.timer.levels) {
  system_gpio_timer_outputs(&board.gpio,board.timer.overrides,board.timer.levels,board.half);
  capture_pins(); pin_voltages();
 }
}
static uint8_t trigger_flags(void) {
 uint8_t flags=0;
 if ((board.gpio.gifr&SYSTEM_INT0) ||
     (!(board.gpio.mcucr&3) && !(board.gpio.digital&2))) flags|=1u<<ANALOG_TRIGGER_INT0;
 if (board.timer.tifr&TIMER0_OCF0A) flags|=1u<<ANALOG_TRIGGER_COMPA;
 if (board.timer.tifr&TIMER0_TOV0) flags|=1u<<ANALOG_TRIGGER_OVERFLOW;
 if (board.timer.tifr&TIMER0_OCF0B) flags|=1u<<ANALOG_TRIGGER_COMPB;
 if (board.gpio.gifr&SYSTEM_PCINT) flags|=1u<<ANALOG_TRIGGER_PCINT;
 return flags;
}
static void sources(void) {
 if (!analog_sources(&board.analog,trigger_flags(),board.half)) fail(DEVICE_FAULT_ANALOG,2);
}
uint16_t device_pending_irqs(void) {
 uint16_t flags=analog_pending(&board.analog);
 uint8_t gpio=system_gpio_pending(&board.gpio), timer=timer0_irq_pending(&board.timer);
 if (gpio&SYSTEM_INT0) flags|=1u<<1;
 if (gpio&SYSTEM_PCINT) flags|=1u<<2;
 if (timer&TIMER0_TOV0) flags|=1u<<3;
 if (nvm_ready_irq(&board.nvm)) flags|=1u<<4;
 if (timer&TIMER0_OCF0A) flags|=1u<<6;
 if (timer&TIMER0_OCF0B) flags|=1u<<7;
 if (system_watchdog_pending(&board.watchdog)) flags|=1u<<8;
 return flags;
}
static void clock_domains(void) {
 uint8_t domains=system_sleep_domains(&board.sleep,board.prr,
  (board.watchdog.control&(SYSTEM_WDE|SYSTEM_WDTIE))!=0);
 int resetting=board.reset_held || reset_starting();
 if (resetting)
  domains&=(uint8_t)~(SYSTEM_CLOCK_CPU|SYSTEM_CLOCK_FLASH|SYSTEM_CLOCK_IO|
                     SYSTEM_CLOCK_ADC|SYSTEM_CLOCK_TIMER0);
 if (domains==board.domains) return;
 int io=(domains&SYSTEM_CLOCK_IO)!=0, adc=(domains&SYSTEM_CLOCK_ADC)!=0;
 int error=timer0_set_clock_enabled(&board.timer,cpu_cycle(),io);
 if (error) fail(DEVICE_FAULT_TIMER,(uint32_t)error);
 if (!analog_adc_clock_running(&board.analog.adc,adc,board.half)) fail(DEVICE_FAULT_ANALOG,3);
 if (!analog_comparator_clock_running(&board.analog.comparator,io,0,board.half))
  fail(DEVICE_FAULT_ANALOG,4);
 if (!analog_comparator_sleep(&board.analog.comparator,
       system_sleep_input_clamp(&board.sleep)||(board.prr&1)||resetting,
       board.half)) fail(DEVICE_FAULT_ANALOG,5);
 system_gpio_sleep(&board.gpio,io,system_sleep_input_clamp(&board.sleep),board.half);
 board.domains=domains;
 capture_pins(); pin_voltages();
}
static void wake(void) {
 if (board.sleep.phase==SYSTEM_SLEEP_ASLEEP) {
  uint16_t pending=device_pending_irqs();
  uint32_t recovery_ns=board.power_enabled?board.power_config[DEVICE_POWER_RECOVERY_NS]:board.config[DEVICE_CFG_BOD_RECOVERY_NS];
  uint64_t recovery=board.bod_disabled ? duration(recovery_ns,base_frequency(),1000000000,0) : 0;
  uint64_t startup=duration(board.config[DEVICE_CFG_WAKE_STARTUP_BASE_HALF],
   base_frequency(),(uint64_t)board.config[DEVICE_CFG_OSCILLATOR_HZ]*2,0);
  uint64_t fuse_startup=source_duration(12);
  if (board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE] &&
      board.sleep.mode==SYSTEM_SLEEP_POWER_DOWN && startup<fuse_startup) startup=fuse_startup;
  /* Explicit profile: oscillator/startup and BOD recovery start concurrently.
   * The CPU waits for both; never double-charge a caller's combined startup. */
  if (recovery>startup) startup=recovery;
  uint8_t status=system_sleep_wake_exact(&board.sleep,pending,pending,
   !(board.gpio.mcucr&3),startup,source_duration(8u*board.divisor),board.base);
  if (status&SYSTEM_SLEEP_INVALID_TIME) fail(DEVICE_FAULT_SLEEP,status);
  if (status&SYSTEM_SLEEP_WAKE_STARTED) {
   if(board.power_enabled) {power_reset_wake(&board.power,board.base);power_sync();}
   if (board.bod_disabled) board.bod_recovery_until=add(board.base,recovery);
   board.bod_disabled=0;
  }
 }
 clock_domains();
}
static void mirror(void) {
 if (!board.data) return;
#define IO(a,v) (board.data[32+(a)]=(uint8_t)(v))
 IO(ANALOG_ADCSRB,board.analog.adc.adcsrb);
 IO(ANALOG_ADCL,(board.analog.adc.admux&AT13_MASK_ADLAR)?board.analog.adc.result<<6:board.analog.adc.result);
 IO(ANALOG_ADCH,(board.analog.adc.admux&AT13_MASK_ADLAR)?board.analog.adc.result>>2:board.analog.adc.result>>8);
 IO(ANALOG_ADCSRA,board.analog.adc.adcsra); IO(ANALOG_ADMUX,board.analog.adc.admux);
 IO(ANALOG_ACSR,board.analog.comparator.acsr);
 IO(SYSTEM_DIDR0,board.gpio.didr0); IO(SYSTEM_PCMSK,board.gpio.pcmsk);
 IO(SYSTEM_PINB,board.gpio.pinb); IO(SYSTEM_DDRB,board.gpio.ddrb); IO(SYSTEM_PORTB,board.gpio.portb);
 IO(SYSTEM_MCUCR,board.gpio.mcucr); IO(SYSTEM_GIFR,board.gpio.gifr); IO(SYSTEM_GIMSK,board.gpio.gimsk);
 IO(SYSTEM_WDTCR,board.watchdog.control); IO(SYSTEM_MCUSR,board.watchdog.mcusr);
 IO(NVM_EECR,board.nvm.eecr); IO(NVM_EEDR,board.nvm.eedr); IO(NVM_EEARL,board.nvm.eearl);
 IO(NVM_SPMCSR,board.nvm.spmcsr);
 IO(TIMER0_PRR,board.prr); IO(TIMER0_GTCCR,board.timer.gtccr);
 IO(TIMER0_TCCR0A,board.timer.tccra); IO(TIMER0_TCCR0B,board.timer.tccrb);
 IO(TIMER0_TCNT0,board.timer.tcnt); IO(TIMER0_OCR0A,board.timer.ocra); IO(TIMER0_OCR0B,board.timer.ocrb);
 IO(TIMER0_TIFR0,board.timer.tifr); IO(TIMER0_TIMSK0,board.timer.timsk);
 IO(CLKPR,board.clkpr);
 IO(BODCR,board.bodcr);
#undef IO
}
static void check_faults(void) {
 if (board.nvm.faults) fail(DEVICE_FAULT_NVM,board.nvm.faults);
 if (board.analog.adc.invalid_reference) fail(DEVICE_FAULT_ANALOG,6);
 if ((board.analog.adc.adcsrb&7)==7) fail(DEVICE_FAULT_ANALOG,7);
 if ((board.analog.comparator.acsr&3)==1) fail(DEVICE_FAULT_ANALOG,8);
 if ((board.watchdog.control&(SYSTEM_WDE|SYSTEM_WDTIE)) && !system_watchdog_period(&board.watchdog))
  fail(DEVICE_FAULT_WATCHDOG,SYSTEM_WDT_RESERVED);
}
static void inputs_at_current_time(void) {
 while (board.input_count && board.inputs[board.input_head].at==board.base) {
  input_t *event=&board.inputs[board.input_head];
  if (!event->type) {
   board.external_mask=event->mask; board.external_levels=event->value;
   system_gpio_external(&board.gpio,event->mask,event->value,board.half);
   external_reset_sync();
  } else if(event->type==1) {
   board.analog_mask|=(uint8_t)(1u<<event->pin);
   board.analog_uv[event->pin]=event->voltage;
   if(board.reset_input_enabled){reset_input_voltage();external_reset_sync();}
  } else {
   board.vcc_uv=event->voltage;supply_guard();
   reset_input_voltage();
   board.raw_other_reset=(uint8_t)((board.raw_other_reset&POWER_RESET_WDRF)|
    (external_reset_asserted()?POWER_RESET_EXTRF:0));
   /* VCC changes the pad receiver's thresholds too. Publish both source
    * changes atomically so POR<->EXTRF cannot briefly release reset. */
   power_reset_set_inputs(&board.power,board.base,board.vcc_uv,board.raw_other_reset);power_sync();
   if(!analog_reference(&board.analog,(uint32_t)board.vcc_uv,board.config[DEVICE_CFG_BANDGAP_UV],board.half))
    fail(DEVICE_FAULT_ANALOG,15);
  }
  board.input_head=(board.input_head+1)%INPUT_CAPACITY; --board.input_count;
  capture_pins(); pin_voltages(); sources();
 }
}
static void service(uint64_t previous_half) {
 deadline_invalidate(DEADLINE_SERVICE);
 system_gpio_t0_event_t t0[4];
 uint8_t edges=system_gpio_advance(&board.gpio,previous_half,board.half,t0);
 if (edges==255) { fail(DEVICE_FAULT_TIME,3); return; }
 if (!analog_advance(&board.analog,board.half)) fail(DEVICE_FAULT_ANALOG,9);
 int error=timer0_advance(&board.timer,cpu_cycle());
 if (error) fail(DEVICE_FAULT_TIMER,(uint32_t)error);
 for (unsigned i=0;i<edges;i++) {
  if (t0[i].half_cycle!=board.half) { fail(DEVICE_FAULT_TIME,4); break; }
  error=timer0_external_edge(&board.timer,t0[i].half_cycle/2,t0[i].edge==SYSTEM_T0_RISING);
  if (error) fail(DEVICE_FAULT_TIMER,(uint32_t)error);
 }
 supply_guard();nvm_advance(&board.nvm,cpu_cycle(),board.ns);
 if(board.reset_input_enabled){
  if(!attiny13a_reset_input_advance(&board.reset_input,board.base))
   fail(DEVICE_FAULT_RESET_INPUT,board.reset_input.fault);
  external_reset_sync();
 }
 if(board.power_enabled) {
  power_reset_advance(&board.power,board.base);power_sync();
  if(board.wdt_reset_end && board.base>=board.wdt_reset_end) {
   board.wdt_reset_end=0;board.raw_other_reset&=(uint8_t)~POWER_RESET_WDRF;power_other_sources();
  }
 }
 /* Internal/external RESET holds the watchdog COUNTER reset. Its oscillator
  * pulses and NVM wall time still advance. Include the ending edge so that
  * the last stretched-reset interval is never counted as normal operation. */
 uint8_t wdt=SYSTEM_WDT_NONE;
 if (board.reset_held || (board.reset_until && board.base<=board.reset_until)) {
  system_watchdog_wdr(&board.watchdog);
  board.watchdog.oscillator_tick=board.wdt_ticks;
  board.watchdog.cpu_cycle=cpu_cycle();
 } else wdt=system_watchdog_advance(&board.watchdog,cpu_cycle(),board.wdt_ticks);
 if (wdt&SYSTEM_WDT_RESET) {
  if(board.power_enabled) {
   board.raw_other_reset|=POWER_RESET_WDRF;power_other_sources();
   board.wdt_reset_end=add(board.base,source_duration(2));
  } else board.reset_requested|=SYSTEM_WDRF;
 }
 if (wdt&(SYSTEM_WDT_RESERVED|SYSTEM_WDT_TIME_REVERSED)) fail(DEVICE_FAULT_WATCHDOG,wdt);
 uint8_t sleep=system_sleep_advance(&board.sleep,board.base);
 if (sleep&SYSTEM_SLEEP_INVALID_TIME) fail(DEVICE_FAULT_SLEEP,sleep);
 if ((board.clkpr&128) && cpu_cycle()>=board.clkpr_until) board.clkpr&=15;
 bod_expire();
 /* Deterministic lower-bound CLKPR transition: the first active edge is one
  * old period after the write; the second is one new period after that edge.
  * Thus the new waveform is established at T1+T2, within section6.3.1's
  * documented range, without inventing an observable hardware ripple phase. */
 if (board.pending_divisor && board.half>=board.clkpr_switch_half) {
  board.divisor=board.pending_divisor; board.pending_divisor=0; board.phase=0;
 }
 timer_outputs(); sources();
 inputs_at_current_time(); wake(); check_faults(); mirror();
}
static uint64_t next_event_scan(void) {
 uint64_t next=at_cycle(timer0_next_event(&board.timer));
 if(board.reset_input_enabled)
  next=minimum(next,attiny13a_reset_input_next_deadline(&board.reset_input));
 if(board.power_enabled) {
  next=minimum(next,power_reset_next_deadline(&board.power));
  if(board.wdt_reset_end) next=minimum(next,board.wdt_reset_end);
 }
 next=minimum(next,at_half(system_gpio_next_event_half(&board.gpio,board.half)));
 next=minimum(next,at_half(analog_next_event(&board.analog)));
 next=minimum(next,at_cycle(nvm_next_event_cycle(&board.nvm)));
 if (board.bod_arm_until) next=minimum(next,at_cycle(board.bod_arm_until));
 if (board.bod_sleep_until) next=minimum(next,at_cycle(board.bod_sleep_until));
 uint64_t ns=nvm_next_event_ns(&board.nvm);
 if (ns!=UINT64_MAX) next=minimum(next,after_units(ns>board.ns?ns-board.ns:0,1000000000,board.ns_remainder));
 if (!board.reset_requested && !board.reset_held && !reset_starting()) {
  uint32_t left=system_watchdog_until_timeout(&board.watchdog);
  if (left) next=minimum(next,after_units(left,board.config[DEVICE_CFG_WATCHDOG_HZ],board.wdt_remainder));
 }
 if (board.watchdog.control&SYSTEM_WDCE) next=minimum(next,at_cycle(board.watchdog.unlock_until));
 if (board.clkpr&128) next=minimum(next,at_cycle(board.clkpr_until));
 if (board.pending_divisor) next=minimum(next,at_half(board.clkpr_switch_half));
 next=minimum(next,system_sleep_next_event(&board.sleep));
 if (reset_starting()) next=minimum(next,board.reset_until);
 if (board.input_count) next=minimum(next,board.inputs[board.input_head].at);
 return next;
}
static uint64_t next_event(void) {
 if (board.deadline.valid && board.deadline.base==board.base)
  return board.deadline.at;
 board.deadline.valid=0;
 uint64_t at=next_event_scan();
 /* at_half/after_units may fail while scanning. A fault is never cached. */
 if (!board.fault) {
  board.deadline.base=board.base; board.deadline.at=at;
  board.deadline.valid=1;
 }
 return at;
}
static void elapse(uint64_t target) {
 deadline_invalidate(DEADLINE_ELAPSE);
 uint64_t delta=target-board.base;
 uint64_t halves=ratio(delta,source_rate(),board.phase,
  base_frequency()*board.divisor,&board.phase);
 board.half=add(board.half,halves);
 board.ns=add(board.ns,rational(delta,1000000000,&board.ns_remainder));
 board.wdt_ticks=add(board.wdt_ticks,rational(delta,board.config[DEVICE_CFG_WATCHDOG_HZ],&board.wdt_remainder));
 board.base=target;
}
static void advance_to(uint64_t target) {
 if (target<board.base) { fail(DEVICE_FAULT_TIME,5); return; }
 if (board.reset_requested) return;
 unsigned stagnant=0;
 do {
  if (board.fault) { if (target>board.base) elapse(target); break; }
  uint64_t next=minimum(next_event(),target), before=board.half, base_before=board.base;
  if (next<board.base) { fail(DEVICE_FAULT_TIME,6); break; }
  elapse(next); service(before);
  /* The CPU bridge aborts the interrupted instruction before later bus effects.
   * Do not consume the rest of its requested span after an asynchronous reset. */
  if (board.reset_requested) break;
  if (board.base==base_before) {
   if (++stagnant>16) { fail(DEVICE_FAULT_TIME,7); break; }
  } else stagnant=0;
  if (board.base==target && next_event()>target) break;
 } while (board.base<=target);
}
int device_configure(uint32_t key, uint32_t value) {
 if (!key || key>=20) return 0;
 if ((key==DEVICE_CFG_OSCILLATOR_HZ || key==DEVICE_CFG_WATCHDOG_HZ) &&
     (!value || value>1000000000)) return 0;
 if ((key==DEVICE_CFG_VCC_UV || key==DEVICE_CFG_BANDGAP_UV) && (value>INT32_MAX || (!value&&key==DEVICE_CFG_BANDGAP_UV))) return 0;
 if (key>=DEVICE_CFG_FUSE_LOW && key<=DEVICE_CFG_LOCK && value>255) return 0;
 if (key==DEVICE_CFG_ADC_FIRST_SAMPLE && value!=27 && value!=29) return 0;
 if (key==DEVICE_CFG_FACTORY_OSCCAL96 && value>127) return 0;
 if (key==DEVICE_CFG_FUSE_STARTUP_PROFILE && value>1) return 0;
 if (key==DEVICE_CFG_NVM_CLOCK_PROFILE && value>DEVICE_NVM_CLOCK_FIXED_NS) return 0;
 if (key==DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ && value>1000000000) return 0;
 configuration[key]=value;
 return 1;
}
int device_configure_power(uint32_t field,uint32_t value) {
 if(field>DEVICE_POWER_FLASH_PROGRAM_MIN_UV) return 0;
 if(field==DEVICE_POWER_ENABLE) {
  if(value>1) return 0;
  if(!value) {power_fields=0;for(unsigned i=0;i<10;i++)power_configuration[i]=0;}
  power_configuration[field]=value;return 1;
 }
 if(field<=DEVICE_POWER_HYSTERESIS_UV || field==DEVICE_POWER_FLASH_PROGRAM_MIN_UV) {
  if(value>INT32_MAX || (!value&&field!=DEVICE_POWER_HYSTERESIS_UV)) return 0;
 }
 power_configuration[field]=value;power_fields|=(uint16_t)(1u<<field);return 1;
}
int device_configure_reset_input(uint32_t field,uint32_t value) {
 if(field>DEVICE_RESET_INPUT_RELEASE_PROPAGATION_NS)return 0;
 if(field==DEVICE_RESET_INPUT_ENABLE){
  if(value>1)return 0;
  if(!value){reset_input_fields=0;for(unsigned i=0;i<7;i++)reset_input_configuration[i]=0;}
 }else{
  if(field<=DEVICE_RESET_INPUT_RELEASE_PPM&&(value<200000||value>900000))return 0;
  reset_input_fields|=(uint8_t)(1u<<field);
 }
 reset_input_configuration[field]=value;return 1;
}
uint8_t device_reset_input_enabled(void){return board.reset_input_enabled;}
uint8_t device_reset_input_asserted(void){
 return board.reset_input_enabled&&(uint8_t)attiny13a_reset_input_asserted(&board.reset_input);
}
uint64_t device_reset_input_deadline_ps(void){
 return board.reset_input_enabled?attiny13a_reset_input_next_deadline(&board.reset_input):UINT64_MAX;
}
int device_configure_osccal_hz(uint32_t cal,uint32_t hz) {
 if (cal>127 || hz>1000000000) return 0;
 calibration_configuration[cal]=hz; calibration_configured=1; return 1;
}
void device_clear_osccal_hz(void) {
 for (unsigned i=0;i<128;i++) calibration_configuration[i]=0;
 calibration_configured=0;
}
int device_init(uint8_t *data, uint8_t *flash, uint8_t *eeprom) {
 board=(device_t){0};
 deadline_invalidate(DEADLINE_INIT);
 for (unsigned i=0;i<20;i++) board.config[i]=configuration[i];
 for (unsigned i=0;i<128;i++) board.calibration[i]=calibration_configuration[i];
 board.physical=calibration_configured;
 board.power_enabled=(uint8_t)power_configuration[DEVICE_POWER_ENABLE];
 board.reset_input_enabled=(uint8_t)reset_input_configuration[DEVICE_RESET_INPUT_ENABLE];
 for(unsigned i=0;i<7;i++)board.reset_input_config[i]=reset_input_configuration[i];
 for(unsigned i=0;i<10;i++)board.power_config[i]=power_configuration[i];
 board.vcc_uv=(int32_t)board.config[DEVICE_CFG_VCC_UV];
 if (!data || !flash || !eeprom) { fail(DEVICE_FAULT_CONFIG,1); return 0; }
 if(board.reset_input_enabled){
  if(!board.physical||reset_input_fields!=0x7e||
     !(board.config[DEVICE_CFG_FUSE_HIGH]&AT13_FUSE_HIGH_DWEN_MASK)){
   fail(DEVICE_FAULT_CONFIG,13);return 0;
  }
  attiny13a_reset_input_profile_t profile={
   .assert_threshold_ppm=board.reset_input_config[DEVICE_RESET_INPUT_ASSERT_PPM],
   .release_threshold_ppm=board.reset_input_config[DEVICE_RESET_INPUT_RELEASE_PPM],
   .assert_qualification_ps=(uint64_t)board.reset_input_config[DEVICE_RESET_INPUT_ASSERT_QUALIFICATION_NS]*1000,
   .release_qualification_ps=(uint64_t)board.reset_input_config[DEVICE_RESET_INPUT_RELEASE_QUALIFICATION_NS]*1000,
   .assert_propagation_ps=(uint64_t)board.reset_input_config[DEVICE_RESET_INPUT_ASSERT_PROPAGATION_NS]*1000,
   .release_propagation_ps=(uint64_t)board.reset_input_config[DEVICE_RESET_INPUT_RELEASE_PROPAGATION_NS]*1000};
  if(!attiny13a_reset_input_init(&board.reset_input,&profile,0,board.vcc_uv,board.vcc_uv)){
   fail(DEVICE_FAULT_RESET_INPUT,board.reset_input.fault);return 0;
  }
 }
 if((!board.vcc_uv&&!board.power_enabled) ||
    (board.power_enabled&&(!board.physical||power_fields!=0x3fe))) {
  fail(DEVICE_FAULT_CONFIG,12);return 0;
 }
 if (board.config[DEVICE_CFG_FUSE_STARTUP_PROFILE] &&
     ((board.config[DEVICE_CFG_FUSE_LOW]>>2)&3)==3) {
  fail(DEVICE_FAULT_CONFIG,8); return 0;
 }
 if (board.physical) {
  uint32_t factory=board.calibration[board.config[DEVICE_CFG_FACTORY_OSCCAL96]];
  unsigned source=board.config[DEVICE_CFG_FUSE_LOW]&3;
  if (!factory) { fail(DEVICE_FAULT_CONFIG,9); return 0; }
  if ((source==1 || source==2) && factory!=board.config[DEVICE_CFG_OSCILLATOR_HZ]) {
   fail(DEVICE_FAULT_CONFIG,10); return 0;
  }
  if (board.config[DEVICE_CFG_NVM_CLOCK_PROFILE] &&
      !board.config[DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ]) {
   fail(DEVICE_FAULT_CONFIG,11); return 0;
  }
 }
 board.data=data; board.flash=flash; board.eeprom=eeprom;
 nvm_timing_t timing=nvm_datasheet_timing(board.config[DEVICE_CFG_FLASH_MAXIMUM]!=0);
 if (!nvm_init(&board.nvm,flash,eeprom,&timing,(uint8_t)board.config[5],
               (uint8_t)board.config[6],(uint8_t)board.config[7])) {
  fail(DEVICE_FAULT_CONFIG,2); return 0;
 }
 system_watchdog_init(&board.watchdog,!(board.config[DEVICE_CFG_FUSE_LOW]&32));
 board.initialized=1;
 if(board.power_enabled) {
  power_reset_profile_t profile={
   .por_assert_uv=(int32_t)board.power_config[DEVICE_POWER_POR_ASSERT_UV],
   .por_release_uv=(int32_t)board.power_config[DEVICE_POWER_POR_RELEASE_UV],
   .bod_center_uv={(int32_t)board.power_config[DEVICE_POWER_BOD00_UV],
    (int32_t)board.power_config[DEVICE_POWER_BOD01_UV],(int32_t)board.power_config[DEVICE_POWER_BOD10_UV]},
   .bod_hysteresis_uv=(int32_t)board.power_config[DEVICE_POWER_HYSTERESIS_UV],
   .bod_filter_ticks=(uint64_t)board.power_config[DEVICE_POWER_FILTER_NS]*1000,
   .timeout_ticks=0,.bod_recovery_ticks=(uint64_t)board.power_config[DEVICE_POWER_RECOVERY_NS]*1000};
  int32_t initial_vcc=board.vcc_uv;board.vcc_uv=0;
  if(!power_reset_init(&board.power,&profile,(uint8_t)board.config[DEVICE_CFG_FUSE_HIGH],0,0)) {
   fail(DEVICE_FAULT_POWER,board.power.fault);return 0;
  }
  power_sync();device_reset(SYSTEM_PORF); /* Acknowledge initial POR without a second reset. */
  board.vcc_uv=initial_vcc;power_reset_set_vcc(&board.power,0,initial_vcc);power_sync();
  analog_reference(&board.analog,(uint32_t)initial_vcc,board.config[DEVICE_CFG_BANDGAP_UV],board.half);
  pin_voltages();mirror();
 } else device_reset(SYSTEM_PORF);
 return !board.fault;
}
static void reset_state(uint8_t sources_mask) {
 board.reset_held=board.power_enabled?board.power.held:(uint8_t)external_reset_asserted();
 board.clkpr=(board.config[DEVICE_CFG_FUSE_LOW]&16)?0:3;
 board.divisor=1u<<board.clkpr; board.phase=0; board.clkpr_until=0; board.prr=0;
 board.pending_divisor=0; board.clkpr_switch_half=0;
 board.bodcr=board.bod_armed=board.bod_committed=board.bod_disabled=0;
 board.bod_arm_until=board.bod_sleep_until=board.bod_recovery_until=0;
 /* Section17.3: hardware always loads the 9.6MHz calibration byte, even
  * when CKSEL selects 4.8MHz. The byte itself is device-specific input. */
 board.data[32+OSCCAL]=(uint8_t)board.config[DEVICE_CFG_FACTORY_OSCCAL96];
 unsigned source=board.config[DEVICE_CFG_FUSE_LOW]&3;
 board.oscillator_hz=board.physical && (source==1 || source==2) ?
  board.calibration[board.data[32+OSCCAL]] : board.config[DEVICE_CFG_OSCILLATOR_HZ];
 timer0_init(&board.timer,NULL,0,cpu_cycle());
 system_gpio_reset(&board.gpio,board.config[DEVICE_CFG_FUSE_HIGH]&1);
 system_gpio_external(&board.gpio,board.external_mask,board.external_levels,board.half);
 analog_comparator_config_t config={board.config[9],board.config[10],0,(uint8_t)board.config[11]};
 analog_reset(&board.analog,(uint32_t)board.vcc_uv,board.config[4],(uint8_t)board.config[8],&config,board.half);
 system_watchdog_reset(&board.watchdog,sources_mask,cpu_cycle(),board.wdt_ticks);
 system_sleep_reset(&board.sleep,board.base);
 nvm_reset(&board.nvm,cpu_cycle(),board.ns);
 if(!board.power_enabled) reset_startup(sources_mask);
 board.domains=0; clock_domains();
 capture_pins(); pin_voltages(); sources(); mirror();
}
void device_reset(uint8_t sources_mask) {
 deadline_invalidate(DEADLINE_RESET);
 if(!board.initialized) return;
 board.reset_requested=0;
 if(board.power_enabled&&board.reset_preapplied) {board.reset_preapplied=0;mirror();return;}
 reset_state(sources_mask);
 if(board.power_enabled&&!board.reset_held) reset_startup(sources_mask);
}
static int timer_register(uint8_t io) {
 return io==TIMER0_GTCCR || io==TIMER0_TCCR0A || io==TIMER0_TCCR0B ||
  io==TIMER0_TCNT0 || io==TIMER0_OCR0A || io==TIMER0_OCR0B ||
  io==TIMER0_TIFR0 || io==TIMER0_TIMSK0;
}
static int programming_clock_known(void) {
 if (!board.physical || (board.config[DEVICE_CFG_NVM_CLOCK_PROFILE]==DEVICE_NVM_CLOCK_FIXED_NS &&
     board.config[DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ])) return 1;
 fail(DEVICE_FAULT_NVM_CLOCK_PROFILE,1); return 0;
}
uint8_t device_read(uint8_t io) {
 deadline_invalidate(DEADLINE_READ);
 uint8_t value=0;
 if (!board.initialized || io>=64) { fail(DEVICE_FAULT_CONFIG,3); return 0; }
 if (io==CLKPR) value=board.clkpr;
 else if (io==BODCR) { bod_expire(); value=board.bodcr; }
 else if (io==TIMER0_PRR) value=board.prr;
 else if (system_gpio_read(&board.gpio,io,&value)) { }
 else if (nvm_owns_io(io)) value=nvm_read_io(&board.nvm,io,cpu_cycle(),board.ns);
 else if (system_watchdog_read(&board.watchdog,io,cpu_cycle(),&value)) { }
 else if (timer_register(io)) {
  int error=timer0_read(&board.timer,cpu_cycle(),io,&value);
  if (error) fail(DEVICE_FAULT_TIMER,(uint32_t)error);
 } else if (io>=ANALOG_ADCSRB && io<=ANALOG_ACSR) {
  if ((board.prr&1) && io!=ANALOG_ACSR) fail(DEVICE_FAULT_ANALOG,10);
  else if (!analog_read(&board.analog,io,&value,board.half)) fail(DEVICE_FAULT_ANALOG,11);
 } else if (io==OSCCAL) value=board.data[32+io]&127;
 else if (io==AT13_IO_SREG || io==AT13_IO_SPL) value=board.data[32+io];
 /* DWDR reads zero without an attached debugger. Reserved addresses read0. */
 board.data[32+io]=value;
 return value;
}
uint32_t device_write(uint8_t io, uint8_t value, uint8_t mask) {
 deadline_invalidate(DEADLINE_WRITE);
 if (!board.initialized || io>=64) { fail(DEVICE_FAULT_CONFIG,4); return 0; }
 if (board.fault || board.reset_requested || board.reset_held || reset_starting() || power_recovering()) return 0;
 uint32_t stalls=0;
 uint8_t previous=board.data[32+io], merged=(previous&(uint8_t)~mask)|(value&mask);
 if (io==CLKPR) {
  if (value&mask&128) {
   if (!(board.clkpr&128) && !(merged&127)) {
    board.clkpr|=128; board.clkpr_until=add(cpu_cycle(),4);
   }
  } else if ((board.clkpr&128) && cpu_cycle()<board.clkpr_until) {
   unsigned code=merged&15;
   if (code>8) fail(DEVICE_FAULT_CLKPR,code);
   else {
    board.clkpr=(uint8_t)code;
    board.pending_divisor=1u<<code;
    board.clkpr_switch_half=multiply(add(cpu_cycle(),1),2);
   }
  }
 } else if (io==TIMER0_PRR) {
  board.prr=merged&3;
  int error=timer0_write(&board.timer,cpu_cycle(),io,board.prr);
  if (error) fail(DEVICE_FAULT_TIMER,(uint32_t)error);
  clock_domains();
 } else if (system_gpio_write_masked(&board.gpio,io,value,mask,board.half)) {
  capture_pins(); pin_voltages();
 } else if (nvm_owns_io(io)) {
  int program=io==NVM_EECR && (value&mask&NVM_EEPE) &&
   (board.nvm.eecr&NVM_EEMPE) && !board.nvm.eeprom_busy && !board.nvm.flash_busy;
  if (!program || programming_clock_known())
   stalls=nvm_write_io(&board.nvm,io,value,mask,cpu_cycle(),board.ns);
  supply_guard();
 }
 else if (system_watchdog_write(&board.watchdog,io,value,mask,cpu_cycle())) { }
 else if (timer_register(io)) {
  uint8_t written=io==TIMER0_TIFR0 ? value&mask : merged;
  if (io==TIMER0_TCCR0B) written=(merged&15)|(value&mask&(AT13_MASK_FOC0A|AT13_MASK_FOC0B));
  int error=timer0_write(&board.timer,cpu_cycle(),io,written);
  if (error) fail(DEVICE_FAULT_TIMER,(uint32_t)error);
  timer_outputs();
 } else if (io>=ANALOG_ADCSRB && io<=ANALOG_ACSR) {
  /* ADCSRA section14.12.2 specifically warns that SBI/CBI can clear ADIF.
   * Preserve that register's actual RMW byte, including its old ADIF=1.
   * ACSR masked writes only strobe ACI when the selected bit writes one. */
  if (io==ANALOG_ACSR) merged=(merged&(uint8_t)~ANALOG_ACI)|(value&mask&ANALOG_ACI);
  if ((board.prr&1) && io!=ANALOG_ACSR) fail(DEVICE_FAULT_ANALOG,12);
  else if (!analog_write(&board.analog,io,merged,board.half)) fail(DEVICE_FAULT_ANALOG,13);
 } else if (io==AT13_IO_SREG || io==AT13_IO_SPL) board.data[32+io]=merged;
 else if (io==OSCCAL) {
  uint8_t cal=merged&127;
  if (cal!=(previous&127)) {
   if (!board.physical) fail(DEVICE_FAULT_UNIMPLEMENTED_IO,OSCCAL);
   else if (!board.calibration[cal]) fail(DEVICE_FAULT_OSCCAL,cal);
   else {
    unsigned source=board.config[DEVICE_CFG_FUSE_LOW]&3;
    if (source==1 || source==2) board.oscillator_hz=board.calibration[cal];
    board.data[32+OSCCAL]=cal;
   }
  } else board.data[32+OSCCAL]=cal;
 } else if (io==BODCR) {
  if (mask&3) bod_write(merged);
 } else if (io!=AT13_IO_DWDR && value&mask) fail(DEVICE_FAULT_UNIMPLEMENTED_IO,io);
 sources(); wake(); check_faults(); mirror();
 return stalls;
}
void device_advance_half(uint64_t halves) {
 if (!board.initialized) { fail(DEVICE_FAULT_CONFIG,5); return; }
 if (board.reset_requested || board.reset_held || reset_starting() || power_recovering()) return;
 uint64_t target=add(board.half,halves);
 if (!halves) { advance_to(board.base); return; }
 while (board.half<target) {
  if (board.fault) {
   /* Preserve the CPU bridge's full-instruction accounting even when the
    * peripheral model stopped at a fault before a pending clock transition. */
   uint64_t end=at_half(target);
   if (end>board.base) elapse(end);
   break;
  }
  uint64_t deadline=at_half(target);
  if (board.pending_divisor) deadline=minimum(deadline,at_half(board.clkpr_switch_half));
  advance_to(deadline);
  if (board.reset_requested) break;
 }
}
void device_advance(uint32_t cycles) { device_advance_half((uint64_t)cycles*2); }
int device_advance_half_until_ps(uint64_t wanted,uint64_t wall,uint64_t *consumed) {
 if(consumed)*consumed=0;
 if(!board.initialized||!consumed){fail(DEVICE_FAULT_CONFIG,14);return -1;}
 if(!time_contract(1,12)||board.fault)return -1;
 if(wall<board.base){fail(DEVICE_FAULT_TIME,12);return -1;}
 if(board.reset_requested)return -1;
 if(board.reset_held||reset_starting()||power_recovering())return 0;
 uint64_t before=board.half,target=add(before,wanted);
 if(board.fault)return -1;
 if(!wanted)advance_to(board.base);
 while(board.half<target&&board.base<wall&&!board.fault&&!board.reset_requested) {
  uint64_t deadline=minimum(at_half(target),wall);
  /* A protected prescaler transition changes the target's physical time.
   * Stop at that edge and recompute rather than overrun or round up halves. */
  if(board.pending_divisor)deadline=minimum(deadline,at_half(board.clkpr_switch_half));
  if(board.fault)break;
  uint64_t previous=board.base;
  advance_to(deadline);
  if(board.base==previous&&!board.fault&&!board.reset_requested) {
   fail(DEVICE_FAULT_TIME,13);break;
  }
 }
 *consumed=board.half-before;
 if(*consumed>wanted){fail(DEVICE_FAULT_TIME,14);return -1;}
 if(board.fault||board.reset_requested)return -1;
 return *consumed==wanted;
}
uint64_t device_next_cpu_event(void) {
 if (!board.initialized || board.fault || board.reset_requested || board.reset_held || reset_starting() || power_recovering()) return 0;
 uint64_t next=next_event();
 if (next==UINT64_MAX) return UINT64_MAX;
 uint64_t remainder;
 uint64_t cycles=ratio(next-board.base,source_rate(),board.phase,
  2*base_frequency()*board.divisor,&remainder);
 return cycles==UINT64_MAX ? UINT64_MAX : cycles+(remainder!=0);
}
uint8_t device_next_irq(void) {
 uint16_t pending=device_pending_irqs();
 for (uint8_t vector=1;vector<10;vector++) if (pending&(1u<<vector)) return vector;
 return 0;
}
void device_ack_irq(uint8_t vector) {
 deadline_invalidate(DEADLINE_IRQ_ACK);
 if (vector==1 || vector==2) system_gpio_ack(&board.gpio,vector);
 else if (vector==3) timer0_irq_ack(&board.timer,TIMER0_TOV0);
 else if (vector==6) timer0_irq_ack(&board.timer,TIMER0_OCF0A);
 else if (vector==7) timer0_irq_ack(&board.timer,TIMER0_OCF0B);
 else if (vector==8) system_watchdog_ack(&board.watchdog);
 else if (vector==5 || vector==9) {
  if (!analog_ack(&board.analog,vector,board.half)) fail(DEVICE_FAULT_ANALOG,14);
 }
 sources(); mirror();
}
uint32_t device_control(uint8_t command, uint16_t z, uint16_t word) {
 deadline_invalidate(DEADLINE_CONTROL);
 if (board.fault || board.reset_requested || board.reset_held || reset_starting() || power_recovering()) return 0;
 if (command==DEVICE_CONTROL_SLEEP) {
  bod_expire();
  uint8_t result=system_sleep_enter(&board.sleep,board.gpio.mcucr,board.base);
  if (result&(SYSTEM_SLEEP_RESERVED|SYSTEM_SLEEP_INVALID_TIME|SYSTEM_SLEEP_BUSY))
   fail(DEVICE_FAULT_SLEEP,result);
  if ((result&SYSTEM_SLEEP_ENTERED) && board.sleep.mode==SYSTEM_SLEEP_POWER_DOWN &&
      ((board.config[DEVICE_CFG_FUSE_HIGH]>>1)&3)!=3 && board.bod_committed &&
      (board.bodcr&2) && cpu_cycle()<board.bod_sleep_until)
   board.bod_disabled=1;
  if(board.power_enabled && (result&SYSTEM_SLEEP_ENTERED)) {
   power_reset_sleep(&board.power,board.base,board.sleep.mode,board.bod_disabled);power_sync();
  }
  clock_domains();
  if (system_sleep_adc_start(&board.sleep))
   analog_adc_noise_cancel_start(&board.analog.adc,board.half);
  wake();
 } else if (command==DEVICE_CONTROL_WDR) system_watchdog_wdr(&board.watchdog);
 else if (command==DEVICE_CONTROL_SPM) {
  uint8_t spm=board.nvm.spmcsr;
  int program=!(board.config[DEVICE_CFG_FUSE_HIGH]&16) && !board.nvm.eeprom_busy &&
   !board.nvm.flash_busy && (spm==3 || spm==5);
  if (program && !programming_clock_known()) return 0;
  int result=nvm_spm(&board.nvm,z,word,cpu_cycle(),board.ns);
  supply_guard();
  if (result<0) fail(DEVICE_FAULT_NVM,board.nvm.faults);
  check_faults(); mirror();
  if (result==NVM_SPM_ERASE || result==NVM_SPM_WRITE) return 0;
  if (!board.config[DEVICE_CFG_SPM_COMMAND_CYCLES]) fail(DEVICE_FAULT_SPM_TIMING,(uint32_t)result);
  return board.config[DEVICE_CFG_SPM_COMMAND_CYCLES];
 } else fail(DEVICE_FAULT_CONFIG,6);
 check_faults(); mirror();
 return 0;
}
uint8_t device_lpm(uint16_t z) {
 deadline_invalidate(DEADLINE_LPM);
 uint8_t value=0xff;
 int special=nvm_lpm(&board.nvm,z,&value,cpu_cycle(),board.ns);
 if (special<0) fail(DEVICE_FAULT_NVM,board.nvm.faults);
 else if (!special) {
  if (z>=1024) fail(DEVICE_FAULT_NVM,0x10000u|z);
  else value=board.flash[z];
 }
 mirror(); return value;
}
int device_halted(void) {
 return board.fault || board.reset_requested || board.reset_held || reset_starting() || power_recovering() || board.sleep.phase!=SYSTEM_SLEEP_RUNNING ||
  nvm_cpu_halted(&board.nvm);
}
uint8_t device_sleep_phase(void) { return board.sleep.phase; }
const device_pin_event_t *device_pin_state(void) {
 return time_contract(0,2) ? &board.pins : NULL;
}
const device_pin_event_ps_t *device_pin_state_ps(void) {
 return time_contract(1,2) ? &board.pins : NULL;
}
static uint64_t wait_until(uint64_t deadline) {
 uint64_t before=cpu_cycle();
 if (deadline<board.base) { fail(DEVICE_FAULT_TIME,8); return 0; }
 while (device_halted() && !board.fault && !board.reset_requested && board.base<deadline) {
  uint64_t next=minimum(next_event(),deadline);
  advance_to(next);
 }
 return cpu_cycle()-before;
}
uint64_t device_wait_until(uint64_t deadline) {
 return time_contract(0,3) ? wait_until(deadline) : 0;
}
uint64_t device_wait_until_ps(uint64_t deadline) {
 if (!time_contract(1,3)) return 0;
 wait_until(deadline); return board.base;
}
static int queue_input(input_t event) {
 deadline_invalidate(DEADLINE_INPUT);
 if (!board.initialized || event.at<board.base || (board.physical&&event.at==UINT64_MAX)) { fail(DEVICE_FAULT_TIME,9); return 0; }
 if (board.input_count==INPUT_CAPACITY) { fail(DEVICE_FAULT_INPUT_OVERFLOW,INPUT_CAPACITY); return 0; }
 if (board.input_count && event.at<board.inputs[(board.input_head+board.input_count-1)%INPUT_CAPACITY].at) {
  fail(DEVICE_FAULT_TIME,10); return 0;
 }
 board.inputs[(board.input_head+board.input_count++)%INPUT_CAPACITY]=event;
 if (event.at==board.base) { inputs_at_current_time(); wake(); mirror(); }
 return 1;
}
int device_inject_digital(uint64_t at, uint8_t mask, uint8_t levels) {
 if (!time_contract(0,4)) return 0;
 input_t event={at,0,0,(uint8_t)(mask&63),(uint8_t)(levels&63),0};
 return queue_input(event);
}
int device_inject_digital_ps(uint64_t at,uint8_t mask,uint8_t levels) {
 if (!time_contract(1,4)) return 0;
 input_t event={at,0,0,(uint8_t)(mask&63),(uint8_t)(levels&63),0};
 return queue_input(event);
}
int device_inject_analog(uint64_t at, uint8_t pin, int32_t uv) {
 if (!time_contract(0,5)) return 0;
 if (pin>5) { fail(DEVICE_FAULT_CONFIG,7); return 0; }
 input_t event={at,uv,1,0,0,pin};
 return queue_input(event);
}
int device_inject_analog_ps(uint64_t at,uint8_t pin,int32_t uv) {
 if (!time_contract(1,5)) return 0;
 if (pin>5) { fail(DEVICE_FAULT_CONFIG,7); return 0; }
 input_t event={at,uv,1,0,0,pin};
 return queue_input(event);
}
int device_inject_vcc_ps(uint64_t at,int32_t uv) {
 if(!time_contract(1,11)) return 0;
 if(!board.power_enabled || uv<0 || at==UINT64_MAX) {fail(DEVICE_FAULT_POWER,6);return 0;}
 input_t event={at,uv,2,0,0,0};return queue_input(event);
}
static const device_pin_event_t *pin_events(uint32_t *count) {
 uint32_t contiguous=PIN_CAPACITY-board.pin_head;
 if (contiguous>board.pin_count) contiguous=board.pin_count;
 *count=contiguous;
 return contiguous ? &board.pin_events[board.pin_head] : NULL;
}
const device_pin_event_t *device_pin_events(uint32_t *count) {
 if (!time_contract(0,6)) { *count=0; return NULL; }
 return pin_events(count);
}
const device_pin_event_ps_t *device_pin_events_ps(uint32_t *count) {
 if (!time_contract(1,6)) { *count=0; return NULL; }
 return pin_events(count);
}
void device_consume_pin_events(uint32_t count) {
 if (count>board.pin_count) count=board.pin_count;
 board.pin_head=(uint16_t)((board.pin_head+count)%PIN_CAPACITY); board.pin_count-=(uint16_t)count;
}
void device_clear_pin_events(void) { board.pin_head=board.pin_count=0; board.dropped=0; }
uint64_t device_dropped_pin_events(void) { return board.dropped; }
uint64_t device_base_half(void) { return time_contract(0,1) ? board.base : 0; }
uint8_t device_physical_mode(void) { return board.physical; }
uint64_t device_time_ps(void) { return time_contract(1,1) ? board.base : 0; }
uint64_t device_cpu_half_deadline_ps(uint64_t halves) {
 return time_contract(1,7) ? at_half(add(board.half,halves)) : 0;
}
uint64_t device_cpu_halves_until_ps(uint64_t deadline) {
 if (!time_contract(1,8) || deadline<=board.base) return 0;
 uint64_t remainder;
 uint64_t halves=ratio(deadline-board.base,source_rate(),board.phase,
  base_frequency()*board.divisor,&remainder);
 return halves==UINT64_MAX ? UINT64_MAX : halves+(remainder!=0);
}
uint64_t device_next_sample_ps(uint64_t start,uint64_t frame,uint32_t rate) {
 if (!time_contract(1,9) || !rate) {
  if (!rate) fail(DEVICE_FAULT_CONFIG,12);
  return 0;
 }
 uint64_t remainder;
 return add(start,ratio(frame,DEVICE_PS_PER_SECOND,0,rate,&remainder));
}
uint64_t device_virtual_half(void) { return board.half; }
uint32_t device_clkpr_divisor(void) { return board.divisor; }
uint32_t device_oscillator_hz(void) { return board.oscillator_hz; }
uint8_t device_power_enabled(void) { return board.power_enabled; }
int32_t device_vcc_microvolts(void) { return board.vcc_uv; }
uint8_t device_bod_disabled(void) { return board.bod_disabled; }
uint8_t device_bod_recovering(void) { return board.base<board.bod_recovery_until; }
uint8_t device_reset_requested(void) { return board.reset_requested; }
uint8_t device_reset_held(void) { return board.reset_held; }
uint8_t device_starting(void) { return (uint8_t)reset_starting(); }
static uint64_t startup_deadline(void) {
 return board.reset_held ? UINT64_MAX : reset_starting() ? board.reset_until : board.base;
}
uint64_t device_startup_deadline(void) { return time_contract(0,10) ? startup_deadline() : 0; }
uint64_t device_startup_deadline_ps(void) { return time_contract(1,10) ? startup_deadline() : 0; }
uint64_t device_flash_generation(void) { return board.nvm.flash_generation; }
uint32_t device_take_dirty_pages(void) { return nvm_take_dirty_pages(&board.nvm); }
uint32_t device_fault(void) { return board.fault; }
uint32_t device_fault_detail(void) { return board.detail; }
