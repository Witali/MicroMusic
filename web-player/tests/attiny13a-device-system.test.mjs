import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {avr,IO,flash,sequential,interruptFixture,sleepFixture} from './fixtures/attiny13a-system-firmware.mjs';

// An optional candidate URL permits cross-worktree integration runs while the
// board/CPU implementation is developed in parallel. Normal runs use the repo.
const deviceURL=process.env.MICROMUSIC_DEVICE_MODULE
  ? pathToFileURL(process.env.MICROMUSIC_DEVICE_MODULE)
  : new URL('../lib/attiny13a.js',import.meta.url);
const {ATtiny13A}=await import(deviceURL.href);
const fast={fuseLow:0x7a,wakeStartupHalf:0}; // CKDIV8 low-fuse bit4 unprogrammed; zero-startup digital profile.
const make=(binary,options={})=>new ATtiny13A(binary,null,{...fast,...options});
const state=c=>c.state();
const cycles=c=>state(c).cycles;

// Official basis: DS40002307A4.7,6.3-6.4,7.1,8.4,9.2-9.3,10.2 and14.12.
// These test the documented digital scheduling profile and public firmware bus;
// they do not claim real-silicon metastability or analog startup measurements.

test('factory CKDIV8 versus playback fuses preserve CPU-to-physical-clock scaling',()=>{
  const rom=sequential([avr.nop(),avr.nop(),avr.nop()]);
  const divided=make(rom,{fuseLow:0x6a}),undivided=new ATtiny13A(rom);
  divided.run(3);undivided.run(3);
  assert.equal(cycles(divided),3);assert.equal(cycles(undivided),3);
  assert.equal(state(divided).clockDivisor,8);assert.equal(state(undivided).clockDivisor,1);
  assert.equal(state(divided).baseHalf,48n);assert.equal(state(undivided).baseHalf,6n);
  assert.equal(divided.readIO(IO.CLKPR)&15,3);assert.equal(undivided.readIO(IO.CLKPR)&15,0);
});

test('firmware IN/OUT/SBI/CBI/LDS/STS/LD/ST share real GPIO bus effects',()=>{
  const instructions=[
    avr.ldi(16,3),avr.out(IO.DDRB,16),avr.out(IO.PORTB,16),avr.nop(),avr.in(17,IO.PINB),
    avr.sbi(IO.PINB,0),avr.in(18,IO.PORTB),avr.cbi(IO.PINB,1),avr.in(19,IO.PORTB),
    avr.ldi(20,3),avr.out(IO.PINB,20),avr.nop(),avr.in(21,IO.PINB),
    avr.lds(22,IO.PINB+32),avr.sts(IO.PINB+32,20),avr.in(23,IO.PORTB),
    avr.ldi(26,IO.PINB+32),avr.ldi(27,0),avr.ldx(24),avr.stx(20),avr.in(25,IO.PORTB),
  ];
  const c=make(sequential(instructions));c.run(instructions.length);
  assert.equal(c.r[17]&3,3);assert.equal(c.r[18]&3,2);assert.equal(c.r[19]&3,2);
  assert.equal(c.r[21]&3,1);assert.equal(c.r[22]&3,1);assert.equal(c.r[23]&3,2);
  assert.equal(c.r[24]&3,2);assert.equal(c.r[25]&3,1);
  assert.equal(c.readIO(IO.PORTB)&3,1);assert.equal(c.data[IO.PORTB+32]&3,1);
  assert.equal(cycles(c),27); // Four 2-cycle data accesses, two 2-cycle bit operations.
});

test('timestamped input changes after sampling preserve PINB half-cycle synchronization',()=>{
  const c=make(sequential([avr.in(16,IO.PINB),avr.in(17,IO.PINB),avr.in(18,IO.PINB),avr.in(19,IO.PINB)]));
  // The board applies equal-timestamp injections after that timestamp's sampling.
  c.injectPins({at:1n,mask:1,levels:1});c.injectPins({at:5n,mask:1,levels:0});
  c.run(4);assert.deepEqual(Array.from(c.r.slice(16,20),v=>v&1),[0,1,1,0]);
  assert.equal(state(c).baseHalf,8n);
  const events=c.drainPins();
  assert.ok(events.some(e=>e.baseHalf===1n&&(e.levels&1)===1));
  assert.ok(events.some(e=>e.baseHalf===5n&&(e.levels&1)===0));
  assert.deepEqual(c.drainPins(),[]);
});

test('INT0 and PCINT flags traverse their synchronization paths before CPU reads',()=>{
  const c=make(sequential(Array.from({length:5},(_,n)=>avr.in(16+n,IO.GIFR))));
  c.writeIO(IO.MCUCR,3);c.writeIO(IO.PCMSK,1);
  c.injectPins({at:3n,mask:3,levels:3});c.run(5);
  assert.deepEqual(Array.from(c.r.slice(16,21),v=>v&0x60),[0,0,0,0x40,0x60]);
  c.writeIO(IO.GIFR,0x40);assert.equal(c.readIO(IO.GIFR)&0x60,0x20);
  c.writeIO(IO.GIFR,0);assert.equal(c.readIO(IO.GIFR)&0x60,0x20);
  c.writeIO(IO.GIFR,0x20);assert.equal(c.readIO(IO.GIFR)&0x60,0);
});

test('simultaneous INT0/PCINT use vector priority, SEI delay and RETI main-instruction delay',()=>{
  const c=make(interruptFixture());c.writeIO(IO.MCUCR,3);c.writeIO(IO.PCMSK,1);c.writeIO(IO.GIMSK,0x60);
  c.injectPins({at:1n,mask:3,levels:3});c.run(9);
  assert.equal(c.pc,24);assert.equal(cycles(c),10);assert.equal(c.readIO(IO.GIFR)&0x60,0x60);
  c.step();assert.equal(c.pc,25);assert.equal(cycles(c),11);assert.equal(c.r[16],0);
  c.step();assert.equal(c.r[16],1);assert.equal(c.pc,1);assert.equal(cycles(c),16);
  assert.equal(c.readIO(IO.SPL),0x9d);assert.equal(c.data[0x9f],26);assert.equal(c.data[0x9e],0);
  assert.equal(c.readIO(IO.SREG)&0x80,0);assert.equal(c.readIO(IO.GIFR)&0x60,0x20);
  c.run(3);assert.equal(c.r[20],1);assert.equal(c.pc,26);assert.equal(cycles(c),23);
  assert.equal(c.r[17],0);assert.equal(c.readIO(IO.SPL),0x9f);
  c.step();assert.equal(c.r[17],1);assert.equal(c.pc,2);assert.equal(cycles(c),28);
  c.run(3);assert.equal(c.r[21],1);assert.equal(c.pc,27);assert.equal(cycles(c),35);
  assert.equal(c.readIO(IO.GIFR)&0x60,0);assert.equal(c.readIO(IO.SPL),0x9f);
});

test('CLI immediately cancels a pending request after SEI',()=>{
  const c=make(sequential([avr.sei(),avr.cli(),avr.nop()]));c.writeIO(IO.GIMSK,0x40);
  c.step();assert.equal(c.pc,1);assert.equal(cycles(c),1);
  c.step();assert.equal(c.pc,2);assert.equal(cycles(c),2);assert.equal(c.readIO(IO.SPL),0x9f);
  assert.equal(c.readIO(IO.SREG)&0x80,0);
});

test('an IRQ arriving inside a block observes ALU flags before a later mainline overwrite',()=>{
  const c=make(flash(
    {instructions:[avr.rjmp(0,16)]},{at:1,instructions:[avr.rjmp(1,64)]},
    {at:16,instructions:[avr.ldi(16,255),avr.ldi(17,1),avr.sei(),avr.nop(),
      avr.add(16,17),avr.eor(19,19),avr.rjmp(22,22)]},
    {at:64,instructions:[avr.in(18,IO.SREG),avr.reti()]},
  ));
  c.r[19]=0x80;c.writeIO(IO.MCUCR,3);c.writeIO(IO.GIMSK,0x40);
  // Input after falling edge9 -> PINB at12 -> INT0 flag at14, exactly when
  // ADD completes. EOR would overwrite ADD's flags in uninterrupted mainline.
  c.injectPins({at:9n,mask:2,levels:2});c.run(8);
  assert.equal(c.r[16],0);assert.equal(c.r[18],0x23);assert.equal(c.r[19],0x80);
  assert.equal(c.pc,65);assert.equal(cycles(c),14);
});

test('SEI followed by SLEEP enters sleep before an already pending interrupt',()=>{
  const c=make(sequential([avr.sei(),avr.sleep(),avr.nop()]));
  c.writeIO(IO.MCUCR,0x20);c.writeIO(IO.GIMSK,0x40); // live INT0 low.
  c.step();assert.equal(c.pc,1);assert.equal(cycles(c),1);
  c.step();assert.equal(c.pc,2);assert.equal(cycles(c),2);
  c.runUntil(20n);assert.equal(c.pc,1);assert.equal(state(c).baseHalf,20n);
  assert.equal(c.readIO(IO.SPL),0x9d);
});

test('firmware CLKPR protected writes change settled clock rates for every divisor',()=>{
  for(let select=0;select<=8;select++) {
    const instructions=[avr.ldi(16,0x80),avr.out(IO.CLKPR,16),avr.ldi(16,select),avr.out(IO.CLKPR,16),
      ...Array.from({length:4},avr.nop)];
    const c=make(sequential(instructions));c.run(6);
    assert.equal(c.readIO(IO.CLKPR)&15,select);assert.equal(state(c).clockDivisor,2**select);
    const at=state(c).baseHalf;c.step();
    assert.equal(state(c).baseHalf-at,2n*BigInt(2**select));
  }
});

test('CLKPCE rewriting does not extend its original four-cycle protection window',()=>{
  const instructions=[avr.ldi(16,0x80),avr.out(IO.CLKPR,16),avr.out(IO.CLKPR,16),
    avr.out(IO.CLKPR,16),avr.out(IO.CLKPR,16),avr.ldi(16,1),avr.out(IO.CLKPR,16)];
  const c=make(sequential(instructions));c.run(instructions.length);
  assert.equal(state(c).clockDivisor,1);assert.equal(c.readIO(IO.CLKPR),0);
});

for(const mode of [0,1,2])test(`sleep mode${mode}: watchdog wakes with explicit startup and4+4 cycle response`,()=>{
  const c=make(sleepFixture(mode));c.run(7);
  assert.equal(state(c).sleeping,true);assert.equal(c.pc,22);assert.equal(c.r[18],0);
  c.runUntil(307199n);assert.equal(state(c).sleeping,true);assert.equal(c.r[18],0);
  c.runUntil(307216n);assert.equal(state(c).sleeping,false);assert.equal(c.pc,8);
  assert.equal(state(c).baseHalf,307216n);assert.equal(c.readIO(IO.SPL),0x9d);
  c.run(3);assert.equal(c.r[20],1);assert.equal(c.pc,22);
  c.step();assert.equal(c.r[18],1);
});

test('watchdog system reset exits Power-down and preserves reset-cause evidence',()=>{
  const c=make(sleepFixture(2,8));c.run(7);assert.equal(state(c).sleeping,true);
  c.runUntil(307200n);
  assert.equal(state(c).resetCount,1);assert.equal(state(c).sleeping,false);
  assert.equal(c.readIO(IO.MCUSR)&9,9);assert.equal(c.readIO(IO.WDTCR)&8,8);
  assert.equal(c.readIO(IO.SPL),0x9f);assert.equal(c.pc,0);
});

test('INT0 low disappearing during explicit startup resumes after SLEEP without its ISR',()=>{
  const c=make(sequential([avr.sei(),avr.sleep(),avr.inc(18)]),{wakeStartupHalf:100});
  c.writeIO(IO.MCUCR,0x30);c.writeIO(IO.GIMSK,0x40);
  c.injectPins({at:0n,mask:2,levels:2});
  c.injectPins({at:10n,mask:2,levels:0});
  c.injectPins({at:20n,mask:2,levels:2});
  c.run(2);assert.equal(state(c).sleeping,true);assert.equal(c.pc,2);
  c.runUntil(120n);
  assert.equal(state(c).sleeping,false);assert.equal(c.r[18],1);
  assert.equal(c.readIO(IO.SPL),0x9f);assert.equal(c.readIO(IO.GIFR)&0x40,0);
});

test('ADCSRA bit-operation interpretation follows its register-specific ADIF warning',()=>{
  // DS40002307A14.12.2 explicitly warns about SBI/CBI clearing ADIF; this
  // conflicts with the generic register-summary bit-only note. The device
  // profile follows the more specific ADC warning, without a silicon claim.
  for(const bitInstruction of [avr.sbi(IO.ADCSRA,3),avr.cbi(IO.ADCSRA,0)]) {
    const instructions=[...Array.from({length:60},avr.nop),bitInstruction,avr.in(16,IO.ADCSRA)];
    const c=make(sequential(instructions));c.writeIO(IO.ADCSRA,0xc0);c.run(60);
    assert.equal(c.readIO(IO.ADCSRA)&0x10,0x10);
    c.run(2);assert.equal(c.r[16]&0x10,0);
  }
});

test('IN, LDS and indirect LD route ADC result locking and ADCH unlock through the bus',()=>{
  const accessors=[
    {name:'IN',read:(d,a)=>[avr.in(d,a)]},
    {name:'LDS',read:(d,a)=>[avr.lds(d,a+32)]},
    {name:'LD X',read:(d,a)=>[avr.ldi(26,a+32),avr.ldi(27,0),avr.ldx(d)]},
  ];
  for(const {name,read} of accessors) {
    const low=read(16,IO.ADCL),high=read(17,IO.ADCH);
    const finalLow=read(18,IO.ADCL),finalHigh=read(19,IO.ADCH);
    const wait=()=>Array.from({length:60},avr.nop);
    const c=make(sequential([...wait(),...low,...wait(),...high,...wait(),...finalLow,...finalHigh]));
    c.writeIO(IO.ADMUX,1);c.writeIO(IO.DIDR0,4);c.writeIO(IO.ADCSRA,0xc0);
    c.run(60);assert.equal(c.readIO(IO.ADCSRA)&0x10,0x10,name+' first conversion');
    c.run(low.length);assert.equal(c.r[16],0,name+' ADCL snapshot');
    c.setAnalog({at:state(c).baseHalf+1n,pin:2,microvolts:5000000});
    c.writeIO(IO.ADCSRA,0xd0);c.run(60);c.run(high.length);
    assert.equal(c.r[17],0,name+' conversion while locked must be dropped');
    c.writeIO(IO.ADCSRA,0xd0);c.run(60);c.run(finalLow.length+finalHigh.length);
    assert.equal(c.r[18],255,name+' unlocked full-scale low byte');
    assert.equal(c.r[19],3,name+' unlocked full-scale high byte');
  }
});
