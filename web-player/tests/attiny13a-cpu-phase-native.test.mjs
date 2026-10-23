import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readdirSync} from 'node:fs';
import {compileAnalog} from './analog-test-build.mjs';

// Compile the real native bridge and board, without an emitter or host imports.
// The fixture supplies the emitter-owned architectural commit/context writes.
const sources=readdirSync(new URL('../native/peripherals/',import.meta.url)).sort()
  .filter(name=>name.endsWith('.c')&&!/(?:^|[.\-_])tests?(?:[.\-_]|$)/i.test(name))
  .map(name=>'web-player/native/peripherals/'+name);
const make=compileAnalog('attiny13a-cpu-phase-native',sources,String.raw`
#define AVR_FULL_DEVICE 1
#include "../avr.c"
#include <string.h>
#define CHECK(expression) do { if (!(expression)) return __LINE__; } while (0)
static int setup(int enabled,int spm) {
 memset(rom,0,sizeof rom);memset(eeprom,255,sizeof eeprom);
 if(!device_configure(DEVICE_CFG_OSCILLATOR_HZ,10000000)||
    !device_configure_osccal_hz(0,10000000)||!device_configure(DEVICE_CFG_FUSE_LOW,0x72)||
    !device_configure(DEVICE_CFG_FUSE_HIGH,spm?0xef:0xff)||
    !device_configure(DEVICE_CFG_SPM_COMMAND_CYCLES,1)||
    !device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,DEVICE_NVM_CLOCK_FIXED_NS)||
    !device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,10000000)||
    !avr_device_phase_enable(enabled))return 0;
 avr_reset(0,0);return !ERROR;
}
static void instruction(int pc,int next) {
 full_phase.active=1;full_phase.exec_pc=(uint32_t)pc;full_phase.next_pc=(uint32_t)next;
 full_phase.stage=0;full_phase.remaining_halves=0;S(pc)=pc;
}
static void ready_irq(int pc) {
 instruction(pc,pc+1);S(pc)=pc+1;FLAGS=128;
 avr_write_io_masked(AT13_IO_EECR,8,255); // Level EEPROM-ready IRQ, vector4.
}
int layout_and_enable(void) {
 CHECK(avr_device_phase_enable(2)==0);CHECK(setup(1,0));
 CHECK(avr_device_phase_layout(1)==80&&avr_device_phase_layout(0)==(uintptr_t)&full_phase);
 const unsigned offsets[]={0,4,8,12,16,24,64,72};
 for(unsigned i=0;i<8;i++)CHECK(avr_device_phase_layout((int)i+2)==(uintptr_t)&full_phase+offsets[i]);
 CHECK(avr_device_phase_layout(10)==0&&avr_device_phase_active()==0);
 CHECK(avr_device_phase_enable(0)==0);return 0;
}
int bounded_fractional_span(void) {
 CHECK(setup(1,0));instruction(10,11);full_phase.locals[3]=0x12345678;full_phase.temp=3.25;
 avr_device_phase_deadline(75001);
 CHECK(avr_device_phase_clock(1.5)==0&&!ERROR&&device_time_ps()==75001);
 CHECK(full_phase.remaining_halves==2&&device_virtual_half()==1&&S(cyc)==0.5);
 CHECK(full_phase.locals[3]==0x12345678&&full_phase.temp==3.25&&S(pc)==10);
 avr_device_phase_deadline(200000);
 CHECK(avr_device_phase_clock(1.5)==1&&!ERROR&&device_time_ps()==150000);
 CHECK(full_phase.remaining_halves==0&&device_virtual_half()==3&&full_phase.retired==0);
 S(pc)=11;avr_device_phase_retire();
 CHECK(!ERROR&&full_phase.retired==1&&avr_device_phase_active()==0&&S(pc)==11);return 0;
}
int exact_deadline_allows_zero_cycle_commit(void) {
 CHECK(setup(1,0));instruction(0,1);avr_device_phase_deadline(100000);
 CHECK(avr_device_phase_clock(1)==1&&device_time_ps()==100000);
 CHECK(avr_device_phase_clock(0)==1&&!ERROR&&device_time_ps()==100000);
 data[0x60]=0x5a;S(pc)=1;avr_device_phase_retire();
 CHECK(!ERROR&&data[0x60]==0x5a&&full_phase.retired==1);
 instruction(1,2);CHECK(avr_device_phase_clock(1)==0&&!ERROR);
 CHECK(device_time_ps()==100000&&full_phase.remaining_halves==2&&full_phase.retired==1);return 0;
}
int direct_board_prescaler_boundary(void) {
 CHECK(setup(0,0));uint64_t consumed=999;
 device_write(AT13_IO_CLKPR,128,255);device_write(AT13_IO_CLKPR,1,255);
 CHECK(device_advance_half_until_ps(6,400000,&consumed)==0&&consumed==5);
 CHECK(device_time_ps()==400000&&device_virtual_half()==5&&device_clkpr_divisor()==2);
 CHECK(device_advance_half_until_ps(1,500000,&consumed)==1&&consumed==1);
 CHECK(device_time_ps()==500000&&device_virtual_half()==6&&!device_fault());return 0;
}
int irq_entry_is_staged_and_resumable(void) {
 CHECK(setup(1,0));ready_irq(0x123);avr_device_phase_deadline(200000);
 avr_device_phase_retire();
 CHECK(!ERROR&&full_phase.retired==1&&full_phase.active==2&&full_phase.stage==1);
 CHECK(device_time_ps()==200000&&SP==158&&data[159]==0x24&&data[158]==0);
 CHECK(full_phase.remaining_halves==2&&S(pc)==0x124&&!(FLAGS&128)&&S(irqCount)==0&&S(frameCount)==0);
 avr_device_phase_deadline(300000);CHECK(avr_device_ready()==0);
 CHECK(!ERROR&&device_time_ps()==300000&&full_phase.active==2&&full_phase.stage==2);
 CHECK(SP==157&&data[158]==1&&S(pc)==0x124&&S(irqCount)==0);
 avr_device_phase_deadline(400000);CHECK(avr_device_ready()==1);
 CHECK(!ERROR&&device_time_ps()==400000&&full_phase.active==0&&S(pc)==4);
 CHECK(SP==157&&S(irqCount)==1&&S(frameCount)==1&&S(inIRQ)==1&&full_phase.retired==1);
 return 0;
}
int irq_wait_can_resume_without_instruction_retirement(void) {
 CHECK(setup(1,0));ready_irq(5);avr_device_phase_deadline(100000);avr_device_phase_retire();
 CHECK(!ERROR&&full_phase.active==2&&SP==159&&full_phase.remaining_halves==2);
 avr_device_phase_deadline(INFINITY);CHECK(avr_device_wait(300000)==1);
 CHECK(!ERROR&&device_time_ps()==300000&&full_phase.active==2&&SP==157&&S(irqCount)==0);
 CHECK(avr_device_wait(400000)==1);
 CHECK(!ERROR&&device_time_ps()==400000&&full_phase.active==0&&S(pc)==4&&S(irqCount)==1&&full_phase.retired==1);
 return 0;
}
int no_arbitration_mid_instruction(void) {
 CHECK(setup(1,0));ready_irq(5);S(irqDelay)=1;avr_device_phase_deadline(50000);
 CHECK(avr_device_phase_clock(1)==0);full_interrupt();
 CHECK(!ERROR&&S(irqDelay)==1&&S(irqCount)==0&&full_phase.active==1&&(FLAGS&128));
 CHECK(avr_device_ready()==1&&S(irqDelay)==1);
 CHECK(avr_device_wait(50000)==0&&S(irqDelay)==1&&S(irqCount)==0);
 avr_device_phase_deadline(INFINITY);CHECK(avr_device_phase_clock(1)==1);S(pc)=6;
 avr_device_phase_retire();CHECK(!ERROR&&S(irqDelay)==0&&S(irqCount)==0&&full_phase.retired==1);
 instruction(6,7);S(pc)=7;avr_device_phase_retire();
 CHECK(!ERROR&&S(pc)==4&&S(irqCount)==1&&full_phase.retired==2);return 0;
}
int async_reset_cancels_instruction_without_error26(void) {
 CHECK(setup(1,0));instruction(10,11);full_phase.retired=7;full_phase.locals[0]=0x5a;
 CHECK(avr_device_inject_pins_ps(125001,32,0));avr_device_phase_deadline(INFINITY);
 CHECK(avr_device_phase_clock(3)==-1&&!ERROR&&device_time_ps()==125001);
 CHECK(full_phase.active==0&&full_phase.remaining_halves==0&&full_phase.stage==0&&full_phase.locals[0]==0);
 CHECK(full_phase.retired==7&&S(pc)==0&&FLAGS==0&&SP==159&&full_reset_count==1);
 CHECK(data[0x60]==0&&device_reset_held());
 avr_reset(0,0);CHECK(!ERROR&&full_phase.retired==0&&full_phase.active==0);return 0;
}
int current_time_reset_cancels_context(void) {
 CHECK(setup(1,0));instruction(10,11);avr_device_phase_deadline(50000);
 CHECK(avr_device_phase_clock(2)==0&&full_phase.remaining_halves==3);
 CHECK(avr_device_inject_pins_ps(50000,32,0));
 CHECK(!ERROR&&full_phase.active==0&&full_phase.remaining_halves==0&&S(pc)==0&&full_reset_count==1);
 return 0;
}
int reset_during_irq_cancels_later_stack_and_vector(void) {
 CHECK(setup(1,0));ready_irq(0x123);avr_device_phase_deadline(200000);avr_device_phase_retire();
 CHECK(!ERROR&&SP==158&&data[159]==0x24&&full_phase.active==2);
 CHECK(avr_device_inject_pins_ps(250001,32,0));avr_device_phase_deadline(INFINITY);
 CHECK(avr_device_ready()==0);
 CHECK(!ERROR&&device_time_ps()==250001&&SP==159&&data[158]==0&&S(pc)==0);
 CHECK(S(irqCount)==0&&S(frameCount)==0&&full_phase.active==0&&full_phase.remaining_halves==0);
 CHECK(full_phase.retired==1&&full_reset_count==1);return 0;
}
int spm_halt_and_generation_do_not_strand_active_instruction(void) {
 CHECK(setup(1,1));instruction(5,6);S(irqDelay)=1;
 avr_write_io_masked(AT13_IO_SPMCSR,3,255);
 CHECK(avr_device_control(DEVICE_CONTROL_SPM,32,0)==0&&device_halted());
 CHECK(avr_device_ready()==1&&S(irqDelay)==1);
 avr_device_phase_deadline(INFINITY);CHECK(avr_device_phase_clock(1)==1&&device_time_ps()==100000);
 CHECK(avr_device_wait(4500000000.0)==1);
 CHECK(!ERROR&&device_flash_generation()!=full_generation&&full_phase.active==1&&S(irqDelay)==1);
 CHECK(avr_device_ready()==1);S(pc)=6;avr_device_phase_retire();
 CHECK(!ERROR&&full_phase.retired==1&&S(irqDelay)==0&&avr_device_ready()==0);
 avr_device_bind_generation();CHECK(avr_device_ready()==1);return 0;
}
int sleep_controller_can_halt_before_retirement(void) {
 CHECK(setup(1,0));instruction(0,1);avr_device_phase_deadline(INFINITY);
 CHECK(avr_device_phase_clock(1)==1);avr_write_io_masked(AT13_IO_MCUCR,32,255);
 CHECK(avr_device_control(DEVICE_CONTROL_SLEEP,0,0)==0&&device_halted());
 CHECK(avr_device_ready()==1&&!ERROR&&full_phase.active==1);
 S(pc)=1;avr_device_phase_retire();CHECK(!ERROR&&full_phase.retired==1&&avr_device_ready()==0);
 return 0;
}
int zero_span_retires_sleep_during_immediate_bod_wake_recovery(void) {
 const uint32_t fields[]={1300000,1400000,4300000,2700000,1800000,50000,20,60000,1800000};
 for(unsigned i=0;i<9;i++)CHECK(device_configure_power(i+1,fields[i]));
 CHECK(device_configure_power(0,1)&&setup(1,0));
 CHECK(device_configure(DEVICE_CFG_FUSE_HIGH,0xfb));avr_reset(0,0);CHECK(!ERROR);
 instruction(0,1);avr_device_phase_deadline(1000000);
 avr_write_io_masked(AT13_IO_MCUCR,48,255); // SE, Power-down, INT0 low-level.
 avr_write_io_masked(AT13_IO_GIMSK,64,255); // Default low PB1 is an immediate wake source.
 avr_write_io_masked(AT13_IO_BODCR,3,255);avr_write_io_masked(AT13_IO_BODCR,2,255);
 CHECK(avr_device_phase_clock(1)==1&&device_time_ps()==100000);
 CHECK(avr_device_control(DEVICE_CONTROL_SLEEP,0,0)==0&&device_bod_recovering()&&device_halted());
 CHECK(avr_device_phase_clock(0)==1&&!ERROR&&device_time_ps()==100000);
 S(pc)=1;avr_device_phase_retire();
 CHECK(!ERROR&&full_phase.active==0&&full_phase.retired==1&&S(pc)==1&&S(irqCount)==0);
 CHECK(avr_device_ready()==0&&avr_device_wait(1000000)==1);
 CHECK(!ERROR&&device_time_ps()==1000000&&device_bod_recovering()&&full_phase.retired==1);
 return 0;
}
int zero_span_preserves_reset_and_fault_priority(void) {
 CHECK(setup(1,0));instruction(0,1);avr_device_phase_deadline(0);
 CHECK(device_inject_digital_ps(0,32,0)&&device_reset_requested());
 CHECK(avr_device_phase_clock(0)==-1&&!ERROR&&full_phase.active==0&&full_phase.retired==0);
 CHECK(S(pc)==0&&device_reset_held()&&full_reset_count==1);
 // A cold reset creates a fresh board; an invalid input then faults it without
 // starting a clock span. No zero-clock completion or retirement may bypass it.
 avr_reset(0,0);CHECK(!ERROR);instruction(0,1);
 CHECK(!device_inject_analog_ps(0,6,0)&&device_fault());
 CHECK(avr_device_phase_clock(0)==-1&&ERROR==25&&full_phase.retired==0);
 return 0;
}
int disabled_legacy_irq_is_unbounded(void) {
 CHECK(setup(0,0));S(pc)=0x124;FLAGS=128;avr_write_io_masked(AT13_IO_EECR,8,255);
 avr_device_phase_deadline(1);full_interrupt();
 CHECK(!ERROR&&S(pc)==4&&S(irqCount)==1&&SP==157&&device_time_ps()==400000);
 CHECK(full_phase.retired==0&&avr_device_phase_active()==0);return 0;
}
int invalid_phase_calls_fault_without_retiring(void) {
 CHECK(setup(1,0));instruction(0,1);avr_device_phase_deadline(NAN);
 CHECK(ERROR==25&&full_phase.retired==0&&device_time_ps()==0);ERROR=0;
 CHECK(avr_device_phase_clock(0.25)==-1&&ERROR==25&&device_time_ps()==0);
 return 0;
}
`);

for(const name of [
  'layout_and_enable','bounded_fractional_span','exact_deadline_allows_zero_cycle_commit',
  'direct_board_prescaler_boundary','irq_entry_is_staged_and_resumable',
  'irq_wait_can_resume_without_instruction_retirement','no_arbitration_mid_instruction',
  'async_reset_cancels_instruction_without_error26','current_time_reset_cancels_context',
  'reset_during_irq_cancels_later_stack_and_vector','spm_halt_and_generation_do_not_strand_active_instruction',
  'sleep_controller_can_halt_before_retirement','disabled_legacy_irq_is_unbounded',
  'zero_span_retires_sleep_during_immediate_bod_wake_recovery','zero_span_preserves_reset_and_fault_priority',
  'invalid_phase_calls_fault_without_retiring',
])test('native CPU phases: '+name.replaceAll('_',' '),()=>{
  const line=make()[name]();assert.equal(line,0,`${name}: inline C assertion failed at line ${line}`);
});
