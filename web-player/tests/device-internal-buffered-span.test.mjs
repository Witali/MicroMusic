import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compileAnalog} from './analog-test-build.mjs';
import {AT13_IO as IO,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';

// compileAnalog creates a unique ignored build/analog-tests directory. This
// fixture never rebuilds or substitutes the production runtime artifact.
const create=compileAnalog('internal-buffered-span',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog','power_reset',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.c"
#include <string.h>
static uint8_t data[160],flash[1024],eeprom[64];
static device_t image;
static uint64_t consumed;
int initialize(int power){
 memset(data,0,sizeof data);memset(flash,255,sizeof flash);memset(eeprom,255,sizeof eeprom);
 device_configure(DEVICE_CFG_OSCILLATOR_HZ,20000000);
 device_configure(DEVICE_CFG_FUSE_LOW,0xf2);
 device_configure(DEVICE_CFG_FUSE_HIGH,power?0xfb:0xff);
 device_configure(DEVICE_CFG_NVM_CLOCK_PROFILE,DEVICE_NVM_CLOCK_FIXED_NS);
 device_configure(DEVICE_CFG_NVM_CALIBRATION_REFERENCE_HZ,20000000);
 device_configure_osccal_hz(0,20000000);
 if(power){
  const uint32_t values[10]={1,1300000,1400000,4300000,2700000,1800000,50000,2000,60000,1800000};
  for(unsigned field=1;field<10;field++)if(!device_configure_power(field,values[field]))return 0;
  if(!device_configure_power(DEVICE_POWER_ENABLE,1))return 0;
 }
 return device_init(data,flash,eeprom);
}
unsigned write(int address,int value){return device_write(address,value,255);}
int observe(int mask,int retain){return device_configure_pin_trace(mask,retain);}
int audio(int mask){return device_configure_audio_pins((uint8_t)mask);}
int span(uint64_t halves,uint64_t wall,int buffered){
 return buffered?device_advance_half_until_ps_buffered(halves,wall,&consumed):
  device_advance_half_until_ps(halves,wall,&consumed);
}
uint64_t used(void){return consumed;}
uint64_t now(void){return device_time_ps();}
uint64_t half(void){return device_virtual_half();}
int fault(void){return device_fault();}
int detail(void){return device_fault_detail();}
unsigned reset_requested(void){return device_reset_requested();}
unsigned divisor(void){return device_clkpr_divisor();}
unsigned pending_divisor(void){return board.pending_divisor;}
unsigned input_count(void){return board.input_count;}
int pins(uint64_t at,int mask,int levels){return device_inject_digital_ps(at,mask,levels);}
int supply(uint64_t at,int uv){return device_inject_vcc_ps(at,uv);}
int sleep_cpu(void){return device_control(DEVICE_CONTROL_SLEEP,0,0);}
int recovering(void){return power_recovering();}
unsigned host_count(void){return board.pin_count;}
unsigned audio_count(void){return board.audio_pin_count;}
unsigned host_ptr(void){uint32_t count;return (unsigned)(uintptr_t)device_pin_events_ps(&count);}
unsigned host_contiguous(void){uint32_t count;device_pin_events_ps(&count);return count;}
unsigned audio_ptr(void){uint32_t count;return (unsigned)(uintptr_t)device_audio_pin_events(&count);}
unsigned audio_contiguous(void){uint32_t count;device_audio_pin_events(&count);return count;}
void consume_host(unsigned count){device_consume_pin_events(count);}
void consume_audio(unsigned count){device_consume_audio_pin_events(count);}
void clear_history(void){device_clear_pin_events();device_consume_audio_pin_events(board.audio_pin_count);}
unsigned architecture(void){
 memcpy(&image,&board,sizeof image);
 // Consuming a history changes only its ring bookkeeping. Compare every other
 // private board byte, including clock remainders, cached deadline, IRQ/source
 // state, peripheral timestamps, reset/sleep and the authoritative live pins.
 image.pin_head=image.pin_count=image.audio_pin_head=image.audio_pin_count=0;
 memset(image.pin_events,0,sizeof image.pin_events);memset(image.audio_pin_events,0,sizeof image.audio_pin_events);
 return (unsigned)(uintptr_t)&image;
}
unsigned architecture_size(void){return sizeof image;}
unsigned data_ptr(void){return (unsigned)(uintptr_t)data;}
unsigned eeprom_ptr(void){return (unsigned)(uintptr_t)eeprom;}
`);

const NEVER=(1n<<64n)-1n;
const PERIOD=50000n; // The explicit20MHz fixture's CPU period in picoseconds.
function make({power=false,mask=63,retain=false,pcm=3}={}){
  const c=create();assert.equal(c.initialize(+power),1);assert.equal(c.fault(),0);
  assert.equal(c.observe(mask,+retain),1);assert.equal(c.audio(pcm),1);
  c.write(IO.DDRB,MASK.DDB0);c.write(IO.OCR0A,0);
  c.write(IO.TCCR0A,MASK.COM0A0|MASK.WGM01);c.write(IO.TCCR0B,MASK.CS00);
  c.clear_history();return c;
}
function records(c,audio=false){
  const prefix=audio?'audio':'host',result=[];
  while(c[prefix+'_count']()){
    const count=c[prefix+'_contiguous'](),pointer=c[prefix+'_ptr']();
    const view=new DataView(c.memory.buffer);
    for(let n=0;n<count;n++){
      const p=pointer+n*16;
      result.push([view.getBigUint64(p,true),...new Uint8Array(c.memory.buffer,p+8,8)]);
    }
    c['consume_'+prefix](count);
  }
  return result;
}
function history(c){return {host:records(c),audio:records(c,true)};}
function append(target,next){target.host.push(...next.host);target.audio.push(...next.audio);}
function architecture(c){return new Uint8Array(c.memory.buffer,c.architecture(),c.architecture_size()).slice();}
function sameHardware(a,b){
  assert.deepEqual(architecture(a),architecture(b));
  for(const [name,size] of [['data',160],['eeprom',64]])
    assert.deepEqual(new Uint8Array(a.memory.buffer,a[name+'_ptr'](),size),
      new Uint8Array(b.memory.buffer,b[name+'_ptr'](),size));
}

for(const {name,wanted,wall,result,count} of [
  {name:'watermark before either endpoint',wanted:2048n,wall:NEVER,result:2,count:512},
  {name:'watermark exactly at the wall',wanted:2048n,wall:512n*PERIOD,result:0,count:512},
  {name:'watermark exactly at request completion',wanted:1024n,wall:NEVER,result:1,count:512},
  {name:'watermark, wall and completion together',wanted:1024n,wall:512n*PERIOD,result:1,count:512},
])test(`internal buffered span: ${name}`,()=>{
  const c=make();assert.equal(c.span(wanted,wall,1),result);
  assert.equal(c.used(),1024n);assert.equal(c.half(),1024n);assert.equal(c.now(),512n*PERIOD);
  assert.equal(c.host_count(),count);assert.equal(c.audio_count(),count);assert.equal(c.fault(),0);
  const events=history(c);assert.equal(events.audio.at(-1)[0],c.now());
  assert.equal(events.audio.at(-1)[1]&1,0,'the512th transition is fully settled');
});

test('fractional wall one picosecond before the watermark retains its final half and phase',()=>{
  const c=make(),reference=make();
  assert.equal(c.span(2048n,512n*PERIOD-1n,1),0);
  assert.equal(c.used(),1023n);assert.equal(c.audio_count(),511);
  assert.equal(c.now(),512n*PERIOD-1n);
  assert.equal(c.span(1n,512n*PERIOD,1),1);assert.equal(c.used(),1n);
  assert.equal(c.audio_count(),512);assert.equal(c.fault(),0);
  assert.equal(reference.span(1024n,512n*PERIOD,0),1);
  assert.deepEqual(history(c),history(reference));sameHardware(c,reference);
});

test('a prefilled watermark yields consumed=0, then draining resumes the unchanged request',()=>{
  const c=make();assert.equal(c.span(1024n,NEVER,0),1);
  const before=architecture(c),time=c.now();
  assert.equal(c.span(256n,NEVER,1),2);assert.equal(c.used(),0n);
  assert.equal(c.now(),time);assert.deepEqual(architecture(c),before);assert.equal(c.fault(),0);
  assert.equal(history(c).audio.length,512);
  assert.equal(c.span(256n,NEVER,1),1);assert.equal(c.used(),256n);
  assert.equal(c.now(),time+128n*PERIOD);assert.equal(c.audio_count(),128);
});

test('ordinary short spans preserve the original path even with an existing watermark',()=>{
  const c=make(),reference=make();
  for(const core of [c,reference])assert.equal(core.span(1024n,NEVER,0),1);
  assert.equal(c.span(128n,NEVER,1),1);assert.equal(c.used(),128n);
  assert.equal(reference.span(128n,NEVER,0),1);
  assert.equal(c.audio_count(),576);assert.deepEqual(history(c),history(reference));sameHardware(c,reference);
});

test('same-time input changes settle and coalesce before the watermark is exposed',()=>{
  const c=make(),reference=make(),at=512n*PERIOD;
  for(const core of [c,reference]){
    assert.equal(core.pins(at,MASK.PCINT1,MASK.PCINT1),1);
    assert.equal(core.pins(at,MASK.PCINT1,0),1);
  }
  assert.equal(c.span(2000n,NEVER,1),2);assert.equal(c.used(),1024n);
  assert.equal(c.input_count(),0);assert.equal(c.now(),at);
  assert.equal(reference.span(1024n,at,0),1);
  const events=history(c);assert.equal(events.audio.length,512);assert.equal(events.host.length,512);
  assert.equal(events.audio.at(-1)[1]&3,0);assert.equal(events.host.at(-1)[1]&3,0);
  assert.deepEqual(events,history(reference));sameHardware(c,reference);
});

test('same-time asynchronous RESET wins over pressure and preserves its exact prefix',()=>{
  const c=make(),reference=make(),at=512n*PERIOD;
  for(const core of [c,reference])assert.equal(core.pins(at,MASK.PCINT5,0),1);
  assert.equal(c.span(2000n,NEVER,1),-1);assert.equal(c.used(),1024n);assert.equal(c.now(),at);
  assert.equal(c.reset_requested(),MASK.EXTRF);assert.equal(c.fault(),0);
  assert.equal(reference.span(2000n,NEVER,0),-1);
  assert.deepEqual(history(c),history(reference));sameHardware(c,reference);
});

test('wrapped total occupancy yields even when its contiguous head is below the watermark',()=>{
  const c=make(),reference=make();
  for(const core of [c,reference]){assert.equal(core.span(1400n,NEVER,0),1);assert.equal(history(core).audio.length,700);}
  assert.equal(c.span(1280n,NEVER,1),2);assert.equal(c.used(),1024n);
  assert.equal(c.audio_count(),512);assert.equal(c.audio_contiguous(),324);
  const actual=history(c);
  assert.equal(c.span(256n,NEVER,1),1);assert.equal(c.used(),256n);append(actual,history(c));
  assert.equal(reference.span(1280n,NEVER,0),1);
  assert.deepEqual(actual,history(reference));sameHardware(c,reference);
});

test('a CLKPR transition inside a long span preserves physical time, all records and fractional state',()=>{
  const c=make(),reference=make();
  for(const core of [c,reference]){core.write(IO.CLKPR,MASK.CLKPCE);core.write(IO.CLKPR,1);}
  assert.equal(c.pending_divisor(),2);
  assert.equal(c.span(1400n,NEVER,1),2);const consumed=c.used();assert.equal(consumed,1024n);
  const actual=history(c);assert.equal(c.divisor(),2);assert.equal(c.pending_divisor(),0);
  assert.equal(c.span(1400n-consumed,NEVER,1),1);append(actual,history(c));
  assert.equal(reference.span(1400n,NEVER,0),1);
  assert.equal(c.used(),376n);assert.equal(c.now(),69950000n);
  assert.deepEqual(actual,history(reference));sameHardware(c,reference);
});

test('retained host history alone is not an undrainable internal BUFFER_READY condition',()=>{
  const c=make({retain:true,pcm:0});
  assert.equal(c.span(1400n,NEVER,1),1);assert.equal(c.used(),1400n);
  assert.equal(c.host_count(),700);assert.equal(c.audio_count(),0);assert.equal(c.fault(),0);
});

test('an ordinary NVM fault after the first drainage retains the original unbuffered endpoint',()=>{
  const c=make({power:true}),reference=make({power:true});
  for(const core of [c,reference]){
    core.write(IO.EEDR,42);core.write(IO.EECR,MASK.EEMPE);core.write(IO.EECR,MASK.EEPE);
    assert.equal(core.supply(600n*PERIOD,1800000),1);
  }
  const wall=1000n*PERIOD;
  assert.equal(c.span(2000n,wall,1),2);const first=c.used();assert.equal(first,1024n);
  const actual=history(c);
  assert.equal(c.span(2000n-first,wall,1),-1);assert.equal(c.used(),976n);append(actual,history(c));
  assert.equal(reference.span(2000n,wall,0),-1);assert.equal(reference.used(),2000n);
  assert.equal(c.fault(),5);assert.equal(c.detail(),128);assert.equal(c.now(),wall);
  assert.equal(actual.audio.at(-1)[0],600n*PERIOD,'the fault stops peripherals before charging the span endpoint');
  assert.equal(new Uint8Array(c.memory.buffer,c.eeprom_ptr(),64)[0],255);
  assert.deepEqual(actual,history(reference));sameHardware(c,reference);
});

test('zero trailing spans retire during actual BOD wake recovery while nonzero spans wait',()=>{
  const c=make({power:true});
  c.write(IO.TCCR0B,0);c.write(IO.MCUCR,MASK.SE|MASK.SM1);c.write(IO.GIMSK,MASK.INT0);
  c.write(IO.BODCR,MASK.BODS|MASK.BODSE);c.write(IO.BODCR,MASK.BODS);
  assert.equal(c.sleep_cpu(),0);assert.equal(c.recovering(),1);
  const before=c.now();assert.equal(c.span(0n,before,1),1);assert.equal(c.used(),0n);
  assert.equal(c.now(),before);assert.equal(c.recovering(),1);assert.equal(c.fault(),0);
  assert.equal(c.span(1000n,NEVER,1),0);assert.equal(c.used(),0n);assert.equal(c.now(),before);
});
