import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';

const old=execFileSync('git',['show','6cb27abb:web-player/native/peripherals/device.c'],{encoding:'utf8'});
const reference=old.match(/uint64_t device_next_cpu_event\(void\) \{[\s\S]*?\n\}/)[0].replace('device_next_cpu_event','reference_cpu_event');
const create=compileAnalog('timer-deadline-budget',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm','analog_adc','analog_comparator','analog','power_reset',
].map(n=>'web-player/native/peripherals/'+n+'.c'),`
#include "device.c"
_Static_assert(sizeof(board.deadline)==24,"deadline metadata must fit existing padding");
static uint8_t data[160],flash[1024],eeprom[64];
${reference}
int initialize(int mode,unsigned hz,int divisor){
 device_configure(1,hz);device_configure(5,mode==2?0x70:0x72);
 if(mode==1){device_configure_osccal_hz(0,hz);device_configure_osccal_hz(1,hz+1);}
 if(mode==2){device_configure_clki(0,1);device_configure_clki(1,1);}
 if(!device_init(data,flash,eeprom))return 0;
 if(mode!=2){device_advance(12);device_write(AT13_IO_CLKPR,128,255);device_write(AT13_IO_CLKPR,divisor,255);device_advance(4);}
 return 1;
}
uint64_t event(void){return next_event();}
uint64_t now(void){return board.base;}
uint64_t half(void){return board.half;}
uint64_t phase_value(void){return board.phase;}
uint64_t rate(void){return source_rate();}
uint64_t denominator(void){return base_frequency()*board.divisor;}
int fault(void){return board.fault;}
int detail(void){return board.detail;}
int valid(void){return board.deadline.valid;}
void cycles(unsigned n){device_advance(n);}
void wait(uint64_t at){device_wait_until_ps(at);}
void write(int a,int v){device_write(a,v,255);}
void pins(uint64_t at){if(board.physical)device_inject_digital_ps(at,4,4);else device_inject_digital(at,4,4);}
void overspeed(void){board.oscillator_hz=board.config[1]*9;deadline_invalidate(DEADLINE_WRITE);}
void distant_timer(void){board.timer.cycle=UINT64_C(0x100000000);deadline_invalidate(DEADLINE_WRITE);}
void exhausted_time(void){board.base=UINT64_MAX-1;board.phase=0;deadline_invalidate(DEADLINE_ELAPSE);}
`);
const unsigned=n=>BigInt.asUintN(64,n),MAX=0xffffffffffffffffn;
const make=(mode=1,hz=9600000,divisor=0)=>{const c=create();assert.equal(c.initialize(mode,hz,divisor),1);return c;};
function budget(c){
  const actual=unsigned(c.device_next_cpu_event()),expected=unsigned(c.reference_cpu_event());assert.equal(actual,expected);
  if(!c.fault()){
    const at=unsigned(c.event()),now=unsigned(c.now());
    assert.equal(actual,at===MAX?MAX:((at-now)*unsigned(c.rate())+unsigned(c.phase_value()))/(2n*unsigned(c.denominator())));
  }
  return actual;
}
for(const mode of [0,1])for(const hz of [1,1000003,9000000,9600000,19999999,20000000])
test(`Timer0 deadline inverse is exact (${mode?'physical':'compatible'}, ${hz} Hz), including odd half phases and CLKPR`,()=>{
  for(const divisor of [0,1,3,8]){
    const c=make(mode,hz,divisor);c.write(IO.TCCR0B,1);c.cycles(4);
    for(let n=0;n<16;n++){
      if(mode)c.wait(c.now()+BigInt(n%7+1));
      budget(c);assert.equal(c.fault(),0);c.cycles(1);
    }
  }
});
test('queued inputs before, tied to and after Timer0 deadlines retain conservative whole-cycle budgets',()=>{
  for(const offset of [-1n,0n,1n]){
    const c=make(1,9000000);c.write(IO.TCCR0B,1);c.cycles(4);const timer=c.event();budget(c);
    c.pins(timer+offset);assert.equal(c.valid(),0);budget(c);assert.equal(c.fault(),0);
  }
});
test('ADC, watchdog, NVM and CLKPR deadlines can supersede the cached Timer0 candidate',()=>{
  for(const configure of [c=>{c.write(IO.ADMUX,3);c.write(IO.ADCSRA,0xe1);},
    c=>c.write(IO.WDTCR,0x40),c=>c.write(IO.EECR,4),c=>c.write(IO.CLKPR,128)]){
    const c=make();c.write(IO.OCR0A,255);c.write(IO.OCR0B,255);c.write(IO.TCCR0B,5);c.cycles(4);budget(c);configure(c);assert.equal(c.valid(),0);
    budget(c);assert.equal(c.fault(),0);
  }
});
test('overspeed and wide synthetic distances retain the original ratio path rather than truncate a budget',()=>{
  for(const change of [c=>c.overspeed(),c=>c.distant_timer()]){
    const c=make(0);c.write(IO.TCCR0B,1);c.cycles(4);change(c);budget(c);assert.equal(c.fault(),0);
  }
});
test('CLKI retains zero admission; scan-time overflow never certifies a finite answer',()=>{
  const external=make(2);external.event();assert.equal(external.device_next_cpu_event(),0n);assert.equal(external.reference_cpu_event(),0n);
  const overflow=make(1,1);overflow.write(IO.TCCR0B,1);overflow.exhausted_time();overflow.device_next_cpu_event();
  assert.equal(overflow.fault(),2);assert.equal(overflow.valid(),0);
});
