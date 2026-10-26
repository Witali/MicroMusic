import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {AT13_DATA as DATA,AT13_MASK as MASK} from '../lib/attiny13a-registers.js';
import {avr,IO,sequential} from './fixtures/attiny13a-system-firmware.mjs';
const moduleURL=process.env.MICROMUSIC_DEVICE_MODULE?pathToFileURL(process.env.MICROMUSIC_DEVICE_MODULE):new URL('../lib/attiny13a.js',import.meta.url);
const {ATtiny13A}=await import(moduleURL.href);
const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
const image=new Uint8Array(1024).fill(255),put=(pc,w)=>{image[2*pc]=w;image[2*pc+1]=w>>8;};
for(const [n,entry] of instructions.entries()){
  let word=parseInt(entry.opcodePattern.replaceAll(' ','').replace(/[^01]/g,'0'),2);
  if(/^(IN|OUT)$/.test(entry.form))word|=(IO.PORTB&15)|((IO.PORTB&48)<<5);
  if(/^(SBI|CBI|SBIC|SBIS)$/.test(entry.form))word|=IO.PORTB<<3;
  put(n*3,word);put(n*3+1,0);
}
const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,optimizeFlags:false,spmCommandCycles:1};
function reset(c,entry,n,flags){
  c._call('avr_reset',0,0);c.pc=n*3;c.sreg=flags;c.r[0]=0x96;c.r[1]=0x69;
  if(entry.form==='RET'||entry.form==='RETI')c.pushPC(1);
  if(entry.form==='POP')c.push(0xa5);
  if(/^(LD|LDD|ST|STD) /.test(entry.form))for(const pointer of [26,28,30])c.r[pointer]=97;
}
for(const optimizePhaseLocals of [false,true]){
  const options={...physical,optimizePhaseLocals},reference=new ATtiny13A(image,null,options),actual=new ATtiny13A(image,null,options);
  for(const [n,entry] of instructions.entries())test(`${entry.form} retires only its documented SREG bits, locals=${optimizePhaseLocals}`,()=>{
    for(const initial of [0x9a,0x65]){
      reset(reference,entry,n,initial);reference.step();assert.equal(reference.state().deviceFault,0);
      const end=reference.state().timePs,edited=initial^255;
      // Generic BSET/BCLR have a variable bit in the catalog mask; this fixture
      // concretizes every operand bit to zero, selecting SREG.C only.
      const mask=/^B(?:SET|CLR)$/.test(entry.form)?1:entry.sregMask;
      const expected=(edited&~mask)|(reference.sreg&mask);
      for(let pause=1n;pause<end;pause+=500000n){
        reset(actual,entry,n,initial);assert.equal(actual.runUntilPs(pause),0);actual.sreg=edited;
        assert.equal(actual.runUntilPs(end),1);assert.equal(actual.sreg,expected,'pause '+pause);
        for(let address=0;address<actual.data.length;address++)if(address!==DATA.SREG)
          assert.equal(actual.data[address],reference.data[address],entry.form+' data '+address);
        assert.equal(actual.pc,reference.pc);assert.equal(actual.cyc,reference.cyc);
        assert.equal(actual.state().cpuPhase.retired,1n);assert.equal(actual.state().timePs,end);
        assert.equal(actual.state().deviceFault,0);
      }
    }
  });
}

for(const [name,words,cycles] of [
  ['OUT',avr.out(IO.SREG,16),1],['STS',avr.sts(DATA.SREG,16),2],['ST X',avr.stx(16),2],
])test(`${name} explicitly writes the complete SREG at its bus boundary`,()=>{
  const c=new ATtiny13A(sequential([words]),null,physical);c.r[16]=0xa5;c.r[26]=DATA.SREG;c.sreg=0x12;
  c.runUntilPs(1n);c.sreg=0x65;assert.equal(c.runUntilPs(BigInt(cycles)*1000000n),1);
  assert.equal(c.sreg,0xa5);assert.equal(c.state().deviceFault,0);
});

for(const [name,words,readAt,end] of [
  ['IN',avr.in(16,IO.SREG),500000n,1000000n],
  ['LDS',avr.lds(16,DATA.SREG),1500000n,2000000n],
  ['LD X',avr.ldx(16),1500000n,2000000n],
])test(`${name} latches its SREG operand but never restores it as flags`,()=>{
  const c=new ATtiny13A(sequential([words]),null,physical);c.r[26]=DATA.SREG;c.sreg=0x12;
  assert.equal(c.runUntilPs(readAt+1n),0);c.sreg=0x65;
  assert.equal(c.runUntilPs(end),1);assert.equal(c.r[16],0x12);assert.equal(c.sreg,0x65);
  assert.equal(c.state().deviceFault,0);
});

const irqCases=[['ADD',avr.add(16,17),1],['BLD',[0xf900],1],['BRNE',[0xf401],2],
  ['RJMP',[0xc000],2],['RCALL',[0xd000],3],['RET',[0x9508],4],
  ['PUSH',[0x930f],2],['POP',[0x910f],2],['IN',avr.in(16,IO.PORTB),1],
  ['OUT',avr.out(IO.PORTB,16),1],['LDS',avr.lds(16,0x60),2],['STS',avr.sts(0x60,16),2],
  ['LD X',avr.ldx(16),2],['ST X',avr.stx(16),2],['LPM',[0x9104],3],
  ['WDR',avr.wdr(),1],['SLEEP',avr.sleep(),1],['BREAK',[0x9598],1],['SPM',[0x95e8],1]];
for(const optimizePhaseLocals of [false,true])for(const [name,words,cycles] of irqCases)
  test(`${name} preserves edited I for a tied IRQ, locals=${optimizePhaseLocals}`,()=>{
    const c=new ATtiny13A(sequential([words]),null,{...physical,optimizePhaseLocals});
    c.r[16]=0xab;c.r[17]=0x5c;c.r[26]=0x60;c.sreg=0;
    if(name==='RET')c.pushPC(1);if(name==='POP')c.push(0xa5);
    c.writeIO(IO.TCNT0,256-cycles);c.writeIO(IO.TIMSK0,MASK.TOIE0);c.writeIO(IO.TCCR0B,1);
    assert.equal(c.runUntilPs(1n),0);c.sreg=MASK.SREG_I|MASK.SREG_T|MASK.SREG_Z|MASK.SREG_C;
    const end=BigInt(cycles)*1000000n;assert.equal(c.runUntilPs(end),1);
    assert.equal(c.state().cpuPhase.active,2);assert.equal(c.sreg&MASK.SREG_I,0);
    if(name==='BLD')assert.equal(c.r[16],0xaa,'BLD uses latched T, not the edited T');
    c.runUntilPs(end+4000000n);assert.equal(c.state().irqs,1);assert.equal(c.state().cpuPhase.retired,1n);
    assert.equal(c.state().deviceFault,0);
  });

for(const optimizePhaseLocals of [false,true])for(const [name,words,cycles] of [
  ['ADD',avr.add(16,17),1],['SET',[0x9468],1],['RETI',avr.reti(),4],
])test(`${name} cannot commit any SREG bits after RESET, locals=${optimizePhaseLocals}`,()=>{
  const c=new ATtiny13A(sequential([words]),null,{...physical,optimizePhaseLocals});
  if(name==='RETI')c.pushPC(1);c.r[16]=0xab;c.r[17]=0x5c;c.sreg=0x12;
  c.runUntilPs(1n);c.sreg=0x65;c.injectPinsPs({at:500000n,mask:32,levels:0});
  assert.equal(c.runUntilPs(BigInt(cycles)*1000000n),0);assert.equal(c.sreg,0);
  assert.equal(c.state().cpuPhase.retired,0n);assert.equal(c.state().resetHeld,true);
  assert.equal(c.r[16],0xab);assert.equal(c.state().deviceFault,0);
});
