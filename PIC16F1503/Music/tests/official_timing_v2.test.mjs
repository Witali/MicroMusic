import test from 'node:test';
import assert from 'node:assert/strict';
import {PIC16F1503} from '../web/pic16-core.mjs';
// PIC16(L)F1503 DS40001607D, Figures 7-2/7-3, Tables 5-2, 27-3,
// and sections 18.1, 19.3, 20.1 and 22.1.
function cpu(...words){const code=new Uint16Array(2048).fill(0);code.set(words);return new PIC16F1503(code);}
function fast(p){p.setMemory(0x099,0x78);p.advanceCycles(1);assert.equal(p.foscHz,16000000);return p;}

test('Reset OSCCON IRCF=0111 is 500 kHz; four oscillator clocks per instruction',()=>{
 const p=cpu(0,0);assert.equal(p.foscHz,500000);
 p.step();assert.equal(p.cycle,1);assert.equal(p.seconds,8e-6);
 p.step();assert.equal(p.seconds,16e-6);
});
test('HFINTOSC clock switch waits approximately 2 microseconds and then TCY=250ns',()=>{
 const p=cpu(0);p.setMemory(0x099,0x78);
 assert.equal(p.foscHz,500000);
 p.advanceCycles(1);assert.equal(p.foscHz,16000000);
 assert.equal(p.seconds,8e-6);
 p.advanceCycles(4);assert.equal(p.seconds,9e-6);
});
test('OSCCON written by instruction takes effect at Q4, not at instruction fetch',()=>{
 const p=cpu(0x0021,0x3078,0x0099,0); // MOVLB1; MOVLW0x78; MOVWF OSCCON; NOP
 p.step();p.step();p.step();assert.equal(p.seconds,24e-6);assert.equal(p.foscHz,500000);
 p.step();assert.equal(p.foscHz,16000000);assert.equal(p.seconds,32e-6);
});
test('IRCF divider selections follow Register 5-1',()=>{
 const table=[[0x78,16000000],[0x70,8000000],[0x68,4000000],[0x60,2000000],[0x58,1000000],[0x50,500000],[0x38,500000],[0x20,62500],[0x00,31000]];
 for(const [osc,want] of table)assert.equal(PIC16F1503.oscillatorFrequency(osc>>3),want);
});
test('Control transfers and taken skips occupy two instruction cycles',()=>{
 for(const word of [0x3200,0x2802,0x2002,0x000b]){
  const p=cpu(word);assert.equal(p.step(),2,'opcode '+word.toString(16));
 }
 const q=cpu(0x180c);q.mem[0x0c]=0;assert.equal(q.step(),2);
 const r=cpu(0x1c0c);r.mem[0x0c]=0;assert.equal(r.step(),1);
});
test('Indirect program Flash reads/writes take additional TCY',()=>{
 const p=cpu(0x3f00);p.setFsr(0,0x8003);p.program[3]=0x3255;
 assert.equal(p.step(),2);assert.equal(p.W,0x55);
 const q=cpu(0x3f80);q.setFsr(0,0x8003);q.W=0xAF;q.program[3]=0x3fff;
 assert.equal(q.step(),2);assert.equal(q.program[3],0x3fff);
});
test('Timer0 FOSC/4 overflow raises TMR0IF regardless of IRQ enable',()=>{
 const p=cpu(0);p.setMemory(0x095,0x08);p.setMemory(0x015,0xfc);
 p.advanceCycles(2);assert.equal(p.mem[0x015],0xfc);
 p.advanceCycles(4);assert.equal(p.mem[0x015],0);assert.equal(p.mem[0x0b]&4,4);
});
test('Timer0 write inhibits precisely next two timer ticks, prescaler resets',()=>{
 const p=cpu(0);p.setMemory(0x095,0x00);p.advanceCycles(3);
 p.setMemory(0x015,10);assert.equal(p.tmr0Prescale,0);
 p.advanceCycles(2);assert.equal(p.mem[0x015],10);
 p.advanceCycles(1);assert.equal(p.mem[0x015],10);
 p.advanceCycles(1);assert.equal(p.mem[0x015],11);
});
test('Timer0 timer clock vs external T0CKI and divider 2/4/256',()=>{
 for(const [opt,div] of [[0x00,2],[0x01,4],[0x07,256],[0x08,1]]){
  const p=cpu(0);p.setMemory(0x095,opt);p.advanceCycles(div-1);assert.equal(p.mem[0x015],0);
  p.advanceCycles(1);assert.equal(p.mem[0x015],1);
 }
 const e=cpu(0);e.advanceCycles(300);assert.equal(e.mem[0x015],0);
});
test('Timer1 FOSC/4 and FOSC sources, prescalers, wrap and flags',()=>{
 for(const [t1con,cycles,want] of [[0x01,2,2],[0x11,4,2],[0x31,8,1],[0x41,2,8],[0x51,2,4]]){
  const p=cpu(0);p.setMemory(0x018,t1con);p.advanceCycles(cycles);
  assert.equal(p.tmr1Value,want,'T1CON '+t1con.toString(16));
 }
 const o=cpu(0);o.setMemory(0x016,0xfe);o.setMemory(0x017,0xff);o.setMemory(0x018,1);
 o.advanceCycles(2);assert.equal(o.tmr1Value,0);assert.equal(o.mem[0x11]&1,1);
});
test('Timer1 LFINTOSC ticks independently of FOSC and can be prescaled',()=>{
 const p=cpu(0);fast(p);p.setMemory(0x018,0xC1);p.advanceCycles(4000000);
 assert.ok(Math.abs(p.tmr1Value-31000)<=1,'LFINTOSC source');
});
test('Timer2 comparator matches PR2, then clears on following prescaled clock',()=>{
 const p=cpu(0);p.setMemory(0x1b,3);p.setMemory(0x1c,0x04);
 p.advanceCycles(3);assert.equal(p.timerCount,3);assert.equal(p.pwmPeriodCount,0);
 p.advanceCycles(1);assert.equal(p.timerCount,0);assert.equal(p.pwmPeriodCount,1);
});
test('Timer2 PR2 changed below TMR2 does not spuriously reset counter',()=>{
 const p=cpu(0);p.setMemory(0x1b,3);p.setMemory(0x1c,0x04);
 p.advanceCycles(2);p.setMemory(0x1b,0);p.advanceCycles(10);
 assert.equal(p.pwmPeriodCount,0);assert.equal(p.timerCount,12);
 p.advanceCycles(244);assert.equal(p.timerCount,0);assert.equal(p.pwmPeriodCount,0);
 p.advanceCycles(1);assert.equal(p.pwmPeriodCount,1);
});
test('Timer2 prescaler 1:4, PR2=1, postscale 1:3 triggers every 24 TCY',()=>{
 const p=cpu(0);p.setMemory(0x1b,1);p.setMemory(0x1c,0x15);
 p.advanceCycles(23);assert.equal(p.mem[0x11]&2,0);
 p.advanceCycles(1);assert.equal(p.mem[0x11]&2,2);
 assert.equal(p.pwmPeriodCount,3);
});
test('PWM3 duty is double-buffered at start of the following PWM period',()=>{
 const p=cpu(0);p.setMemory(0x1b,63);p.setMemory(0x1c,0x04);p.setMemory(0x619,0xc0);
 p.setMemory(0x618,32);p.advanceCycles(64);assert.equal(p.samples[0],128);
 p.setMemory(0x618,8);p.advanceCycles(5);assert.equal(p.samples.length,1);
 p.advanceCycles(59);assert.equal(p.samples[1],32);
});
test('PWM edge events represent physical 16 MHz FOSC ticks, 50% pulse 8us',()=>{
 const p=cpu(0);fast(p);p.capturePwmEdges=true;
 p.setMemory(0x08C,0);p.setMemory(0x18C,0);
 p.setMemory(0x1b,63);p.setMemory(0x1c,0x04);
 p.setMemory(0x619,0xC0);p.setMemory(0x618,32);
 p.advanceCycles(64);assert.equal(p.pwmPinLevel,1);
 const rise=p.pwmEdges.at(-1);assert.equal(rise.level,1);
 p.advanceCycles(32);assert.equal(p.pwmPinLevel,0);
 const fall=p.pwmEdges.at(-1);
 assert.equal(fall.level,0);assert.equal(fall.timePs-rise.timePs,8e6);
});
test('PWM3 pin gate respects TRISA/ANSELA; reverse polarity 50% falls then rises',()=>{
 const p=cpu(0);fast(p);p.capturePwmEdges=true;
 p.setMemory(0x1b,63);p.setMemory(0x1c,0x04);
 p.setMemory(0x619,0xe0);p.setMemory(0x618,32);
 p.advanceCycles(64);assert.equal(p.pwmEdges.length,0,'default TRISA input blocks RA2');
 p.setMemory(0x08c,0);p.setMemory(0x18c,0);p.advanceCycles(64);
 assert.equal(p.pwmPinLevel,0);p.advanceCycles(32);assert.equal(p.pwmPinLevel,1);
});
test('Interrupt eligibility Timer0, Timer1, Timer2 and two bubble cycles',()=>{
 for(const [name,flags,enables,intcon] of [['TMR0',0,0,0xA4],['TMR1',1,1,0xC0],['TMR2',2,2,0xC0]]){
  const p=cpu(0x0000,0,0,0,0x0009);
  p.mem[0x0b]=intcon;
  p.mem[0x011]=flags;
  p.mem[0x091]=enables;
  p.step();assert.equal(p.PC,4,name);assert.equal(p.cycle,3,name);
  assert.equal(p.irqSourceCounts[name],1);
  p.mem[0x011]=0;p.mem[0x0b]&=~4;p.step();assert.equal(p.PC,1);
 }
});
test('RETFIE is two cycles, no unwanted immediate nested IRQ',()=>{
 const p=cpu(0,0,0,0,0x0009);
 p.mem[0x0b]=0xC0;p.mem[0x091]=2;p.mem[0x11]=2;
 p.step();assert.equal(p.cycle,3);
 p.mem[0x11]=0;p.step();assert.equal(p.cycle,5);assert.equal(p.inIRQ,false);
});
test('Legacy CLRWDT/OPTION/TRISA one-cycle semantics',()=>{
 const p=cpu(0x0064,0x0062,0x0065);
 p.mem[3]=0;p.W=0x00;p.step();assert.equal(p.mem[3]&0x18,0x18);
 p.W=0x08;p.step();assert.equal(p.mem[0x095],0x08);
 p.W=0x31;p.step();assert.equal(p.mem[0x08C],0x31);
 assert.equal(p.cycle,3);
});

test('10-bit PWM3 1-tick pulse lasts exactly one FOSC clock, not one instruction',()=>{
 const p=cpu(0);fast(p);p.capturePwmEdges=true;
 p.setMemory(0x08C,0);p.setMemory(0x18C,0);
 p.setMemory(0x1b,63);p.setMemory(0x1c,4);p.setMemory(0x619,0xC0);
 p.setMemory(0x618,0);p.setMemory(0x617,0x40); // 10-bit duty=1
 p.advanceCycles(64);const start=p.pwmEdges.at(-1);
 p.advanceCycles(1);const fall=p.pwmEdges.at(-1);
 assert.equal(fall.timePs-start.timePs,62500); // 1/16 MHz = 62.5 ns
});
test('TMR0 write from MOVWF is applied at Q4, with two subsequent inhibited cycles',()=>{
 const p=cpu(0x300F,0x0095,0,0,0);
 p.setMemory(0x095,0x08);p.step();assert.equal(p.mem[0x15],1);
 p.step();assert.equal(p.mem[0x15],15);
 p.step();p.step();assert.equal(p.mem[0x15],15);
 p.step();assert.equal(p.mem[0x15],16);
});
test('PWM register writes from instruction are latched one cycle later at the period boundary',()=>{
 const p=cpu(0x0098);fast(p);p.bsr=12;
 p.setMemory(0x1b,63);p.setMemory(0x1c,4);p.setMemory(0x619,0xC0);
 p.setMemory(0x618,32);p.W=16;p.advanceCycles(63);
 p.step();assert.equal(p.samples[0],128); // old value latched on 64th tick
 p.advanceCycles(64);assert.equal(p.samples[1],64); // Q4 write visible next period
});
test('OSCSTAT stable/ready tracks the nominal clock switching delay',()=>{
 const p=cpu(0);p.setMemory(0x099,0x78);
 assert.equal(p.mem[0x09a]&0x11,0); // still on 500 kHz
 p.advanceCycles(1);assert.equal(p.mem[0x09a]&0x11,0x11);
 p.setMemory(0x09a,0);assert.equal(p.mem[0x09a]&0x11,0x11); // read-only
});
test('Timer1 external T1CKI cannot silently masquerade as internal clock',()=>{
 const p=cpu(0);p.setMemory(0x18,0x81);p.advanceCycles(20);
 assert.equal(p.tmr1Value,0,'no external pulses injected');
 p.setMemory(0x19,0x80);assert.throws(()=>p.advanceCycles(1),/Timer1 gated mode/);
});
test('Software RESET executes in one cycle without resetting simulated time history',()=>{
 const p=cpu(0x0001);const t0=p.timePs;
 assert.equal(p.step(),1);assert.equal(p.PC,0);assert.equal(p.cycle,1);
 assert.ok(p.timePs>t0);assert.equal(p.totalInstructions,1);
});
