import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
const configuration=mode=>({fuseHigh:0xef,spmCommandCycles:4,...(mode==='physical'?physical:{})});
function image(){
  const write=(io,v)=>[...avr.ldi(16,v),...avr.out(io,16)],target=0x100;
  const words=[...avr.ldi(30,0),...avr.ldi(31,1),...write(IO.SPMCSR,3),0x95e8];
  for(const [n,w] of [avr.ldi(20,0x5a)[0],avr.ldi(21,0xa5)[0],0xcfff].entries())
    words.push(...avr.ldi(30,2*n),...avr.ldi(16,w&255),0x2e00,...avr.ldi(16,w>>8),0x2e10,...write(IO.SPMCSR,1),0x95e8);
  words.push(...avr.ldi(30,0),...write(IO.SPMCSR,5),0x95e8,0xcfff);
  return flash({instructions:[words]},{at:128,instructions:[avr.ldi(20,0x11),avr.ldi(21,0x22),[0xcfff]]});
}
// Use the already supported timed runner to start the actual firmware's page
// write, then complete it with the public manual clock API. No host ROM edits.
function finishWrite(c,mode){
  if(mode==='physical')c.runUntilPs(4700000000n);else c.runUntil(90000n);
  assert.equal(c._exports.avr_device_generation(),1n);assert.equal(c._generation,1n);
  assert.equal(c.state().halted,true,'The firmware must have started the second SPM operation');
  c.debugEnabled=true;c.eeprom[3]=0x63;c.clock(100000);
  assert.equal(c._exports.avr_device_generation(),2n);assert.equal(c.state().halted,false);
  assert.deepEqual(Array.from(c.rom.slice(256,260)),[0x4a,0xe5,0x55,0xea]);
  c.pc=128;
}
function execute(c,entry,mode){
  const cycles=c.cyc,retired=c.state().cpuPhase?.retired;
  if(entry==='step')assert.equal(c.step(),undefined);
  else if(entry==='run')assert.equal(c.run(2),2);
  else assert.equal(c.runBlock(),true);
  const count=entry==='step'?1:2;
  assert.equal(c.r[20],0x5a,'Execute newly written code on this first API call');
  assert.equal(c.r[21],count===1?0:0xa5);assert.equal(c.pc,128+count);assert.equal(c.cyc-cycles,count);
  if(mode==='physical')assert.equal(c.state().cpuPhase.retired-retired,BigInt(count));
  assert.equal(c._generation,2n);assert.equal(c.debugEnabled,true);assert.equal(c.eeprom[3],0x63);
  assert.equal(c.state().deviceFault,0);
}
for(const incrementalCompilation of [false,true])for(const mode of ['compatible','physical'])
  for(const entry of mode==='compatible'?['step','run','block']:['step','run'])
    test(`completed SPM refreshes before ${entry}, ${mode}, incremental${incrementalCompilation}`,()=>{
      const c=new ATtiny13A(image(),null,{...configuration(mode),incrementalCompilation});
      finishWrite(c,mode);execute(c,entry,mode);
    });

for(const incrementalCompilation of [false,true])test(`precompiled packages resume a manual-clock SPM write, incremental${incrementalCompilation}`,async()=>{
  const options=configuration('compatible'),a=new ATtiny13A(image(),null,options);
  const pkg=await createPackage({flash:a.rom,configuration:options,runtime:getRuntimeBytes(),translated:a.transpiledBytes,manifest:a.transpilation});
  const c=await ATtiny13A.fromPackage(pkg,{incrementalCompilation});finishWrite(c,'compatible');execute(c,'step','compatible');
});

test('invalid instruction limits still fail before compilation or virtual clock changes',()=>{
  const c=new ATtiny13A(image(),null,configuration('compatible'));finishWrite(c,'compatible');
  const before={generation:c._generation,pc:c.pc,cycles:c.cyc,module:c._translatedModule};
  for(const n of [-1,NaN,Infinity,.5,0x80000000])assert.throws(()=>c.run(n),/Invalid instruction count/);
  assert.equal(c._generation,before.generation);assert.equal(c._translatedModule===before.module,true);
  assert.equal(c.pc,before.pc);assert.equal(c.cyc,before.cycles);
});

for(const mode of ['compatible','physical'])test(`timed runners retain SPM completion and physical retirement counts (${mode})`,()=>{
  const c=new ATtiny13A(image(),null,configuration(mode));
  if(mode==='physical'){
    const before=c.state().cpuPhase.retired,result=c.runUntilPs(11000000000n);
    assert.equal(BigInt(result),c.state().cpuPhase.retired-before);assert.equal(c._generation,2n);
  }else{c.runUntil(220000n);assert.equal(c._generation,2n);}
  assert.equal(c.state().deviceFault,0);
});
