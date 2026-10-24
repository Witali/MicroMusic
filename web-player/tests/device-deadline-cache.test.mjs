import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync,execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {compileAnalog} from './analog-test-build.mjs';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {AT13_IO as IO} from '../lib/attiny13a-registers.js';
import {parseHex} from '../lib/hex.js';
import {avr,sequential} from './fixtures/attiny13a-system-firmware.mjs';

// Include the actual production implementation once. The private scanner is
// the oracle on this same board; there is no copied scheduler/state mirror.
const create=compileAnalog('deadline-cache',[
  'timer0','system_gpio','system_watchdog','system_sleep','nvm',
  'analog_adc','analog_comparator','analog','power_reset',
].map(name=>`web-player/native/peripherals/${name}.c`),`
#include "device.c"
static uint8_t data[160],flash[1024],eeprom[64];
int initialize(int physical,int supply,unsigned hz,int high) {
 for(unsigned i=0;i<1024;i++)flash[i]=255;
 for(unsigned i=0;i<64;i++)eeprom[i]=255;
 device_configure(1,hz);device_configure(6,high);device_configure(13,2);
 if(physical){device_configure_osccal_hz(0,hz);device_configure_osccal_hz(1,hz+1);
  device_configure(18,1);device_configure(19,hz);}
 if(supply){const uint32_t p[]={1,1300000,1400000,4300000,2700000,1800000,50000,2000,60000,1800000};
  for(unsigned i=0;i<10;i++)if(!device_configure_power(i,p[i]))return 0;}
 return device_init(data,flash,eeprom);
}
uint64_t cached(void){return next_event();}
uint64_t scan(void){return next_event_scan();}
int valid(void){return board.deadline.valid;}
uint64_t now(void){return board.base;}
uint64_t half(void){return board.half;}
uint64_t phase_value(void){return board.phase;}
void cycles(unsigned n){device_advance(n);}
void zero_elapse(void){elapse(board.base);}
void zero_service(void){service(board.half);}
unsigned write(int address,int value,int mask){return device_write(address,value,mask);}
int read(int address){return device_read(address);}
void ack(int vector){device_ack_irq(vector);}
void control(int command,int z,int word){device_control(command,z,word);}
int lpm(int z){return device_lpm(z);}
void reset_cpu(int causes){device_reset(causes);}
int pins(uint64_t at,int mask,int levels){return board.physical?device_inject_digital_ps(at,mask,levels):device_inject_digital(at,mask,levels);}
int analog(uint64_t at,int pin,int uv){return board.physical?device_inject_analog_ps(at,pin,uv):device_inject_analog(at,pin,uv);}
int vcc(uint64_t at,int uv){return device_inject_vcc_ps(at,uv);}
void wait(uint64_t at){if(board.physical)device_wait_until_ps(at);else device_wait_until(at);}
int requested(void){return device_reset_requested();}
int held(void){return device_reset_held();}
int preapplied(void){return board.reset_preapplied;}
int fault(void){return device_fault();}
int detail(void){return device_fault_detail();}
int count_pins(void){uint32_t n;pin_events(&n);return n;}
void consume(void){device_consume_pin_events(1000000);}
void clear_pins(void){device_clear_pin_events();}
unsigned dirty(void){return device_take_dirty_pages();}
int peek(int address){return data[32+address];}
int ee(int address){return eeprom[address];}
`);
const make=({physical=0,supply=0,hz=9600000,high=0xef}={})=>{
  const c=create();assert.equal(c.initialize(physical,supply,hz,high),1);return c;
};
const put=(c,address,value,mask=255)=>c.write(address,value,mask);
function prime(c){assert.equal(c.fault(),0);const result=c.cached();assert.equal(result,c.scan());assert.equal(c.valid(),1);return result;}
function mutation(c,operation){prime(c);operation();assert.equal(c.valid(),0,'mutation must invalidate before another query');
  assert.equal(c.cached(),c.scan());assert.equal(c.valid(),c.fault()?0:1);}

test('cached infinity, repeated public budgets and output-history queries retain an unchanged state',()=>{
  const c=make();c.cycles(12);assert.equal(prime(c),-1n);
  for(let n=0;n<8;n++){assert.equal(c.cached(),-1n);assert.equal(c.scan(),-1n);assert.equal(c.valid(),1);}
  assert.ok(c.count_pins());c.consume();assert.equal(c.valid(),1);c.clear_pins();assert.equal(c.valid(),1);
  assert.equal(c.dirty(),0);assert.equal(c.valid(),1);assert.equal(c.cached(),c.scan());
});
test('elapse and service invalidate even at zero time; normal endpoints republish current state',()=>{
  const c=make();prime(c);c.zero_elapse();assert.equal(c.valid(),0);prime(c);
  c.zero_service();assert.equal(c.valid(),0);prime(c);c.cycles(0);assert.equal(c.cached(),c.scan());
  c.cycles(19);assert.equal(c.cached(),c.scan());assert.equal(c.half(),38n);
});
test('timer, GPIO, ADC, comparator, PRR, protected clock and reset bus transactions dirty same-base state',()=>{
  const c=make();c.cycles(12);
  for(const [address,value] of [[IO.DDRB,3],[IO.OCR0A,31],[IO.OCR0B,7],[IO.TCCR0A,0xa3],
    [IO.TCCR0B,1],[IO.TCNT0,252],[IO.GTCCR,129],[IO.GTCCR,0],[IO.PRR,1],[IO.PRR,0],
    [IO.PCMSK,4],[IO.PINB,1],[IO.DIDR0,4],[IO.MCUCR,3],[IO.ADMUX,1],
    [IO.ADCSRB,3],[IO.ADCSRA,0xa0],[IO.ACSR,0x40],[IO.GIFR,0x60],[IO.TIMSK0,14],
    [IO.CLKPR,128],[IO.CLKPR,3],[IO.BODCR,3],[IO.BODCR,2],[IO.SREG,128],[IO.SPL,159]])
    mutation(c,()=>put(c,address,value));
  mutation(c,()=>c.read(IO.ADCL));mutation(c,()=>c.read(IO.WDTCR));mutation(c,()=>c.read(IO.BODCR));
  for(const vector of [1,2,3,5,6,7,8,9])mutation(c,()=>c.ack(vector));
  mutation(c,()=>c.reset_cpu(8));
});
test('CLKPR transition and OSCCAL rate changes with retained phase cannot reuse an old absolute event',()=>{
  const c=make({physical:1});c.cycles(12);put(c,IO.TCCR0B,1);prime(c);
  mutation(c,()=>put(c,IO.CLKPR,128));mutation(c,()=>put(c,IO.CLKPR,3));c.cycles(3);
  assert.equal(c.cached(),c.scan());assert.notEqual(c.phase_value(),0n);
  mutation(c,()=>put(c,IO.OSCCAL,1));c.cycles(7);assert.equal(c.cached(),c.scan());
  mutation(c,()=>c.reset_cpu(2));assert.equal(c.peek(IO.OSCCAL),0);
});
test('future/current digital and analog inputs invalidate insertion, head consumption and source propagation',()=>{
  const c=make();c.cycles(12);
  mutation(c,()=>assert.equal(c.pins(c.now(),1,1),1));
  mutation(c,()=>assert.equal(c.analog(c.now(),0,1000000),1));
  mutation(c,()=>assert.equal(c.pins(c.now()+3n,4,4),1));
  mutation(c,()=>assert.equal(c.analog(c.now()+8n,2,2500000),1));
  c.cycles(5);assert.equal(c.cached(),c.scan());assert.equal(c.fault(),0);
});
test('special LPM consumes a cached fuse window and NVM programming replaces CPU windows with wall deadlines',()=>{
  const c=make();c.cycles(12);put(c,IO.SPMCSR,9);assert.notEqual(prime(c),-1n);
  mutation(c,()=>assert.equal(c.lpm(0),0x7a));assert.equal(c.cached(),-1n);
  put(c,IO.EEARL,4);put(c,IO.EEDR,42);mutation(c,()=>put(c,IO.EECR,4));
  mutation(c,()=>assert.equal(put(c,IO.EECR,2),2));assert.notEqual(c.cached(),-1n);
  c.cycles(32640);assert.equal(c.ee(4),42);assert.equal(c.cached(),c.scan());
  put(c,IO.SPMCSR,1);mutation(c,()=>c.control(2,0,0x1234));
  put(c,IO.SPMCSR,3);mutation(c,()=>c.control(2,0,0));assert.notEqual(c.cached(),-1n);
});
test('watchdog WDR/ACK, sleep entry and exact wake events invalidate their future deadlines',()=>{
  const c=make();c.cycles(12);put(c,IO.WDTCR,0x40);c.cycles(100);
  const before=prime(c);mutation(c,()=>c.control(3,0,0));assert.ok(c.cached()>before);
  mutation(c,()=>c.ack(8));put(c,IO.MCUCR,0x30);mutation(c,()=>c.control(1,0,0));
  c.wait(c.now()+400000n);assert.equal(c.cached(),c.scan());assert.equal(c.fault(),0);
});
test('power input reset is preapplied at assertion and acknowledgment invalidates its same-time cache',()=>{
  const c=make({physical:1,supply:1,hz:10000000,high:0xeb});put(c,IO.DDRB,1);put(c,IO.PORTB,1);
  mutation(c,()=>assert.equal(c.vcc(37n,0),1));c.cycles(4);
  assert.equal(c.now(),37n);assert.equal(c.requested(),1);assert.equal(c.preapplied(),1);assert.equal(c.peek(IO.DDRB),0);
  mutation(c,()=>c.reset_cpu(c.requested()));assert.equal(c.preapplied(),0);assert.equal(c.held(),1);
  mutation(c,()=>assert.equal(c.vcc(1000000n,5000000),1));c.wait(1000000n);assert.equal(c.held(),0);
  assert.equal(c.cached(),c.scan());assert.equal(c.fault(),0);
});
test('same-time supply uncertainty removes an earlier NVM completion and is never cached as a healthy state',()=>{
  const c=make({physical:1,supply:1,hz:10000000,high:0xeb});c.cycles(12);
  put(c,IO.EEARL,4);put(c,IO.EEDR,42);put(c,IO.EECR,4);put(c,IO.EECR,2);
  assert.notEqual(prime(c),-1n);mutation(c,()=>assert.equal(c.vcc(c.now(),1800000),1));
  assert.equal(c.fault(),5);assert.equal(c.detail(),128);assert.equal(c.ee(4),255);assert.equal(c.valid(),0);
});
test('fault during a scan cannot publish its result or revive a stale answer',()=>{
  const c=make({physical:1,hz:1});c.cycles(18446744);assert.equal(prime(c),-1n);
  put(c,IO.TCCR0B,1);assert.equal(c.fault(),0);c.cached();
  assert.equal(c.fault(),2);assert.equal(c.detail(),1);assert.equal(c.valid(),0);
  c.cached();assert.equal(c.valid(),0);assert.equal(c.detail(),1);
});
test('read/input validation faults clear a primed cache without replacing their first fault',()=>{
  for(const operation of [c=>c.read(64),c=>c.pins(c.now()-1n,1,1)]){
    const c=make();c.cycles(12);prime(c);operation(c);assert.equal(c.valid(),0);
    assert.ok(c.fault());const detail=c.detail();c.cached();assert.equal(c.valid(),0);assert.equal(c.detail(),detail);
  }
});

// Actual committed pre-cache runtime, not a test-only reimplementation. Keeping
// the Git blob avoids versioning a second large binary and keeps this oracle
// meaningful after the normal shipped runtime is rebuilt with the cache.
const root=fileURLToPath(new URL('../../',import.meta.url));
const baseline=execFileSync('git',['show','f4aec2f:web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:1024*1024});
const sha=value=>createHash('sha256').update(value).digest('hex');
assert.equal(baseline.length,94758);assert.equal(sha(baseline),'2f44f950d742c66fbae466e1673da08a97ef893adcfc8ed404cc77ca2b726413');
const build=spawnSync(process.execPath,['web-player/scripts/build-device-wasm.mjs','--out-dir','build/deadline-cache-test/runtime'],{cwd:root,encoding:'utf8'});
assert.equal(build.status,0,build.stderr||String(build.error));
const candidate=readFileSync(join(root,'build/deadline-cache-test/runtime/attiny13a.wasm'));
const modules=[baseline,candidate].map(binary=>new WebAssembly.Module(binary));
function cores(image,options={}){return modules.map(runtimeModule=>new ATtiny13A(image,null,{...options,runtimeModule}));}
function parity(pair,{conservativeIdle=false}={}){
  const [a,b]=pair,oldState=a.state(),newState=b.state();
  if(conservativeIdle){
    // The smaller safe event budget can skip fewer wait-loop cycles. This
    // counts optimized work, not CPU time: total cycles/PC/IRQ/pins still match.
    assert.ok(newState.idleCycles>=0&&newState.idleCycles<=oldState.idleCycles);
    assert.ok(newState.idleCycles<=newState.cycles);newState.idleCycles=oldState.idleCycles;
  }
  assert.deepEqual(newState,oldState);assert.deepEqual(b.data,a.data);
  assert.deepEqual(b.rom,a.rom);assert.deepEqual(b.eeprom,a.eeprom);assert.deepEqual(Array.from(b.irqFrames),Array.from(a.irqFrames));
  const actual=Array.from(b._state),expected=Array.from(a._state),hint=b._fieldIndex.overflowAt;
  assert.equal(hint,a._fieldIndex.overflowAt);
  // The historical runtime rounded this private scheduling hint up. The
  // current conservative floor fixes physical RESET endpoint ties. Validate
  // that exact policy difference; all chip state and other diagnostics match.
  if(actual[hint]!==expected[hint])assert.equal(actual[hint],expected[hint]-1);
  actual[hint]=expected[hint];
  if(conservativeIdle)actual[b._fieldIndex.idleCycles]=expected[a._fieldIndex.idleCycles];
  assert.deepEqual(actual,expected);assert.equal(b.state().deviceFault,0);
}
const catalog=['firmware.json','hq4-firmware.json'].flatMap(path=>JSON.parse(readFileSync(new URL('../'+path,import.meta.url))).entries);
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-auto'])test(`actual baseline raw PCM/CPU/peripheral parity: ${id}`,()=>{
  const entry=catalog.find(entry=>entry.id===id),image=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  const pair=modules.map(runtimeModule=>new ATtiny13A(image,eeprom,{runtimeModule,oscillatorHz:entry.cpuHz||9600000}));
  for(const c of pair){c.injectPins({at:777n,mask:4,levels:4});c.setAnalog({at:1601n,pin:2,microvolts:1234567});}
  for(let frames=0;frames<2048;frames+=128){
    const raw=pair.map(c=>c.capturePhysical(128,48000,entry.audioChannels||1));
    assert.ok(Buffer.from(raw[0].buffer).equals(Buffer.from(raw[1].buffer)));parity(pair);
  }
  assert.deepEqual(pair[0].drainPins(),pair[1].drainPins());
});
const table=Array(128).fill(0);table[0]=10000000;table[1]=10100000;
const power={porAssertMicrovolts:1300000,porReleaseMicrovolts:1400000,bod00Microvolts:4300000,
  bod01Microvolts:2700000,bod10Microvolts:1800000,bodHysteresisMicrovolts:50000,bodFilterNs:2000,
  bodRecoveryNs:60000,flashProgrammingMinMicrovolts:1800000};
const physical={oscillatorHz:10000000,osccalHz:table,powerResetProfile:power,fuseLow:0x72,fuseHigh:0xfb,
  nvmClockProfile:1,nvmCalibrationReferenceHz:10000000};
test('actual baseline physical phase/OSCCAL/CLKPR, queued inputs and pin traces match',()=>{
  const pair=cores(sequential([avr.rjmp(0,0)]),physical);
  for(const c of pair){c.writeIO(IO.DDRB,3);c.writeIO(IO.OCR0A,191);c.writeIO(IO.OCR0B,63);
    c.writeIO(IO.TCCR0A,0xa3);c.writeIO(IO.TCCR0B,1);c.injectPinsPs({at:377777n,mask:4,levels:4});
    c.setAnalogPs({at:999999n,pin:2,microvolts:2345678});c.clock(7);c.writeIO(IO.OSCCAL,1);
    c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,2);c.clock(7);}
  parity(pair);assert.deepEqual(pair[0].drainPinsPs(),pair[1].drainPinsPs());
  const raw=pair.map(c=>c.capturePhysical(37,44100,2));assert.ok(Buffer.from(raw[0].buffer).equals(Buffer.from(raw[1].buffer)));
  parity(pair,{conservativeIdle:true});
});
test('actual baseline supply reset abort/hold/release, BOD filtering and physical capture match',()=>{
  const pair=cores(sequential([avr.ldi(16,0x5a),avr.sts(0x60,16),avr.rjmp(3,0)]),physical);
  for(const c of pair){c.step();c.setVccPs({at:c.state().timePs+37n,microvolts:0});c.step();}
  parity(pair);assert.equal(pair[1].data[0x60],0);assert.equal(pair[1].state().resetHeld,true);
  for(const c of pair){c.setVccPs({at:1000000n,microvolts:5000000});c.runUntilPs(1000000n);
    c.setVccPs({at:2000000n,microvolts:2600000});c.runUntilPs(4000000n);}
  parity(pair);assert.equal(pair[1].state().resetHeld,true);
  for(const c of pair){c.setVccPs({at:5000000n,microvolts:5000000});c.runUntilPs(5000000n);c.writeIO(IO.DDRB,2);c.writeIO(IO.PORTB,2);
    c.setVccPs({at:36250000n,microvolts:0});}
  assert.deepEqual(pair[0].drainPinsPs(),pair[1].drainPinsPs());
  const raw=pair.map(c=>c.capturePhysical(3,8000));assert.ok(Buffer.from(raw[0].buffer).equals(Buffer.from(raw[1].buffer)));parity(pair);
});
