import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {AVRCore} from '../lib/avr-transpiled.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {parseHex} from '../lib/hex.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {avr,IO,flash,sequential} from './fixtures/attiny13a-system-firmware.mjs';
import {put} from './helpers/avr-test-state.mjs';
const hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,spmCommandCycles:1};
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),eeprom:c.eeprom.slice(),
  flash:c.rom.slice(),irq:Array.from(c.irqFrames),control:c.controlRequest,watchdog:c.watchdogResetCycle,debug:c.debugEnabled});
const same=(a,b,label)=>{assert.deepEqual(snapshot(a),snapshot(b),label);assert.equal(a.state().deviceFault,0);};
const pair=(image,options={})=>[false,true].map(incrementalCompilation=>new ATtiny13A(image,null,{fastIdle:false,...options,incrementalCompilation}));
const patch=(cores,pc,word)=>{for(const c of cores){put(c.rom,pc,word);c._compile();}};

test('incremental code shares modules but isolates globals, tables, memory and diagnostics',()=>{
  const image=sequential([avr.ldi(16,16),avr.inc(17)]),a=new ATtiny13A(image,null,{incrementalCompilation:true});
  const b=new ATtiny13A(image,null,{incrementalCompilation:true});
  assert.equal(b.translationCacheHit,true);assert.equal(b.incrementalCompilation.compiled,0);
  assert.equal(a._translatedModule,b._translatedModule);assert.notEqual(a._translated.cpuTable,b._translated.cpuTable);
  assert.notEqual(a._translated.debugEnabled,b._translated.debugEnabled);assert.notEqual(a._exports.memory,b._exports.memory);
  a.debugEnabled=true;a.transpilation.abi.data=0;a.transpiledBytes.fill(0);a.incrementalCompilation.groups=0;
  b.run(2);assert.equal(b.r[16],16);assert.equal(b.r[17],1);assert.equal(b.debugEnabled,false);
  assert.ok(b.transpilation.abi.data>0);assert.equal(b.incrementalCompilation.groups,33);
  const module=b._translatedModule,unchanged=b._incremental.instances.get('page/1').exports;
  put(b.rom,0,avr.ldi(16,17)[0]);b._compile();b.pc=0;b.step();assert.equal(b.r[16],17);
  assert.equal(b._translatedModule,module);assert.equal(b._incremental.instances.get('page/1').exports,unchanged);
  assert.equal(b.incrementalCompilation.compiled,1);assert.equal(b.incrementalCompilation.reusedModules,32);
  assert.equal(b.incrementalCompilation.instantiated,1);assert.equal(b.incrementalCompilation.changedSlots,17);
  assert.equal(b.incrementalCompilation.emittedInstructions,2);assert.equal(b.incrementalCompilation.emittedBlocks,1);
});

for(const [pc,operand] of [[15,16],[511,0]])test(`two-word fetch dependencies wrap correctly at word${pc}`,()=>{
  const image=new Uint8Array(1024).fill(255);put(image,pc,avr.lds(20,0x60)[0]);put(image,operand,0x60);
  const cores=pair(image),c=cores[1],old=c._incremental.instances;
  patch(cores,operand,0x61);
  for(const core of cores){core.pc=pc;core.data[0x61]=0xa5;core.step();}
  same(...cores,'operand patch');assert.equal(c.r[20],0xa5);assert.deepEqual(c.transpiledBytes,cores[0].transpiledBytes);
  // Both operand words decode to the same unsupported standalone instruction;
  // only the LDS fetch dependency needs a different executable fragment.
  const affected=new Set([Math.floor(pc/16)]);
  for(let page=0;page<32;page++)assert.equal(c._incremental.instances.get('page/'+page).module===old.get('page/'+page).module,!affected.has(page));
});

for(const word of [0x1001,0xfc00,0x9900])test(`skip width invalidates the preceding page (${word.toString(16)})`,()=>{
  const image=new Uint8Array(1024).fill(255);put(image,15,word);put(image,16,0);put(image,17,0x60);
  const cores=pair(image),c=cores[1],old=c._incremental.instances.get('page/0').module;
  patch(cores,16,avr.lds(20,0x60)[0]);assert.notEqual(c._incremental.instances.get('page/0').module,old);
  for(const core of cores){core.pc=15;core.r[0]=core.r[1]=0;core.step();}same(...cores,'skip width');assert.equal(c.pc,18);
});

test('a remote branch target change invalidates affected block layout outside the written page',()=>{
  const image=new Uint8Array(1024).fill(0);put(image,80,avr.rjmp(80,20)[0]);put(image,511,avr.rjmp(511,511)[0]);
  const cores=pair(image),c=cores[1],old=c._incremental.instances.get('page/1').module;
  patch(cores,80,avr.rjmp(80,21)[0]);assert.notEqual(c._incremental.instances.get('page/1').module,old);
  for(const core of cores)assert.equal(core.run(160),160);same(...cores,'branch leaders');
  assert.deepEqual(c.transpiledBytes,cores[0].transpiledBytes);
});

test('cross-page cyclic regions rebind unchanged wrappers and remove obsolete dispatch entries',()=>{
  const image=flash({at:14,instructions:[avr.inc(20),avr.inc(21),avr.inc(22),avr.rjmp(17,14)]});
  const cores=pair(image,{...physical,boundedRegions:true,optimizePhaseLocals:true}),c=cores[1];
  const wrapper=c._incremental.instances.get('wrappers/0'),body=c._incremental.instances.get('page/0');
  patch(cores,16,avr.inc(23)[0]);
  assert.notEqual(c._incremental.instances.get('page/0').module,body.module,'Region depends on its entire SCC');
  assert.notEqual(c._incremental.instances.get('wrappers/0').module,wrapper.module,'Detach the original wrapper from its static seed callee');
  assert.notEqual(c._incremental.instances.get('wrappers/0').exports,wrapper.exports,'Changed callee must be rebound');
  for(const core of cores){core.pc=14;core.run(51);}same(...cores,'cyclic registers');assert.ok(c.r[23]>0);
  const rebound=c._incremental.instances.get('wrappers/0');patch(cores,16,avr.inc(24)[0]);
  assert.equal(c._incremental.instances.get('wrappers/0').module,rebound.module,'Reuse the specialized wrapper module');
  assert.notEqual(c._incremental.instances.get('wrappers/0').exports,rebound.exports,'Bind its new region body');
  for(const core of cores){core.pc=14;core.run(51);}same(...cores,'rebound wrapper');assert.ok(c.r[24]>0);
  patch(cores,17,avr.rjmp(17,32)[0]);assert.equal(c.transpilation.regions.length,0);
  assert.ok(![...c._incremental.instances.keys()].some(id=>id.startsWith('wrappers/')));
  for(const core of cores){core.pc=14;core.run(4);}same(...cores,'removed region');assert.equal(c.pc,32);
});

test('LPM observes changed Flash data even when its own fragment is reused',()=>{
  const image=flash({instructions:[[0x9144]]},{at:128,instructions:[[0x1234]]}),cores=pair(image);
  const c=cores[1],old=c._incremental.instances.get('page/0').module;
  patch(cores,128,0x5678);assert.equal(c._incremental.instances.get('page/0').module,old);
  for(const core of cores){core.r[30]=0;core.r[31]=1;core.step();}same(...cores,'live LPM');assert.equal(c.r[20],0x78);
});

test('changing a page outside a cyclic region preserves its original seeded wrappers',()=>{
  const image=flash({at:14,instructions:[avr.inc(20),avr.inc(21),avr.rjmp(16,14)]},{at:128,instructions:[avr.ldi(20,1)]});
  const cores=pair(image,{...physical,boundedRegions:true}),c=cores[1],wrapper=c._incremental.instances.get('wrappers/0');
  patch(cores,128,avr.ldi(20,2)[0]);assert.equal(c._incremental.instances.get('wrappers/0').exports,wrapper.exports);
  assert.equal(c.incrementalCompilation.compiled,1);
  for(const core of cores){core.pc=14;core.run(51);}same(...cores,'unaffected seed wrapper');
});

test('changes to compiler policy cannot reuse old emitted instruction or block templates',()=>{
  const cores=pair(sequential([avr.add(16,17),avr.eor(16,18),avr.inc(19)]),physical);
  for(const c of cores){c._translationOptions.optimizeFlags=false;c._translationOptions.maxBlockInstructions=2;c._compile();c.run(3);}
  same(...cores,'new compiler policy');assert.equal(cores[1].incrementalCompilation.emittedInstructions,512);
  assert.deepEqual(cores[0].transpiledBytes,cores[1].transpiledBytes);
});

const {instructions}=JSON.parse(readFileSync(new URL('../reports/attiny13a-instructions.json',import.meta.url)));
const all=new Uint8Array(1024).fill(255);
for(const [n,e] of instructions.entries()){
  let word=parseInt(e.opcodePattern.replaceAll(' ','').replace(/[^01]/g,'0'),2);
  if(/^(IN|OUT)$/.test(e.form))word|=(IO.PORTB&15)|((IO.PORTB&48)<<5);
  if(/^(SBI|CBI|SBIC|SBIS)$/.test(e.form))word|=IO.PORTB<<3;
  put(all,n*3,word);put(all,n*3+1,0);
}
for(const external of [false,true])test(`all123 forms retain phases, four C/Z inputs and bounded output (CLKI${external})`,()=>{
  const cores=pair(all,{...physical,optimizePhaseLocals:true,boundedRegions:true,...(external?{osccalHz:undefined,
    fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{})});
  assert.deepEqual(cores[0].transpiledBytes,cores[1].transpiledBytes);
  for(const [n,e] of instructions.entries())for(let flags=0;flags<4;flags++){
    for(const c of cores){
      c._call('avr_reset',0,0);c.pc=n*3;c.sreg=0x70|flags;c.r[0]=0x96;c.r[1]=0x69;
      if(e.form==='RET'||e.form==='RETI')c.pushPC(1);
      if(e.form==='POP')c.push(0xa5);
      if(/^(LD|LDD|ST|STD) /.test(e.form))for(const p of [26,28,30])c.r[p]=97;
    }
    let at=0n,level=1;
    const edges=Array.from({length:20},()=>{at+=external?(level?700000n:300000n):500000n;level^=1;return{timePs:at,level};});
    if(external)for(const c of cores)assert.equal(c.injectClkiPs({edges,knownUntilPs:at}),true);
    let retired=0;
    for(const edge of edges){
      for(const deadline of [edge.timePs-1n,edge.timePs]){
        const count=cores[0].runUntilPs(deadline);assert.equal(cores[1].runUntilPs(deadline),count);retired+=count;
        same(...cores,e.form+' / '+flags+' / '+deadline);assert.deepEqual(cores[0].drainPinsPs(),cores[1].drainPinsPs());
      }
      if(retired)break;
    }
    assert.equal(retired,1,e.form);
  }
});

test('RESET at each RCALL half phase cancels the same bus and stack effects',()=>{
  for(let half=0n;half<=6n;half++){
    const cores=pair(sequential([[0xd000]]),physical);
    for(const c of cores){c.data[0x9f]=0xa5;c.injectPinsPs({at:half*500000n,mask:32,levels:0});}
    for(let at=1n;at<=3500001n;at+=250000n){assert.equal(cores[0].runUntilPs(at),cores[1].runUntilPs(at));same(...cores,'reset '+half);}
    assert.deepEqual(cores[0].drainPinsPs(),cores[1].drainPinsPs());
  }
});

function selfProgrammingImage(){
  const write=(io,v)=>[...avr.ldi(16,v),...avr.out(io,16)],target=0x100,newWords=[avr.ldi(20,0x5a)[0],0xcfff];
  const words=[...avr.ldi(30,0),...avr.ldi(31,1),...write(IO.SPMCSR,3),0x95e8];
  for(const [n,w] of newWords.entries())words.push(...avr.ldi(30,2*n),...avr.ldi(16,w&255),0x2e00,
    ...avr.ldi(16,w>>8),0x2e10,...write(IO.SPMCSR,1),0x95e8);
  words.push(...avr.ldi(30,0),...write(IO.SPMCSR,5),0x95e8);
  words.push(avr.rjmp(words.length,target/2)[0]);
  return flash({instructions:[words]},{at:target/2,instructions:[avr.ldi(20,0x11),[0xcfff]]});
}
for(const clock of ['compatible','physical','clki'])test(`real SPM replaces only affected compiled fragments (${clock})`,()=>{
  const options={fuseHigh:0xef,spmCommandCycles:4,cacheTranslation:false,...(clock==='compatible'?{}:{...physical,
    nvmClockProfile:1,nvmCalibrationReferenceHz:hz,...(clock==='clki'?{osccalHz:undefined,fuseLow:0x70,
      clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{})})};
  const cores=pair(selfProgrammingImage(),options),c=cores[1],shell=c._translatedModule,untouched=c._incremental.instances.get('page/0');
  for(const core of cores){
    if(clock==='clki')core.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:500000n,lowPs:500000n,
      transitionCount:40000n,knownUntilPs:20000000000n});
    if(clock==='compatible')core.runUntil(200000n);
    else if(clock==='physical')core.runUntilPs(20000000000n);
    else for(let at=200000000n;at<=20000000000n;at+=200000000n){core.runUntilPs(at);core.drainPinsPs();}
  }
  same(...cores,'SPM '+clock);assert.equal(c.r[20],0x5a);assert.equal(c._exports.avr_device_generation(),2n);
  assert.equal(c._translatedModule,shell);assert.equal(c._incremental.instances.get('page/0').exports,untouched.exports);
  assert.equal(c.incrementalCompilation.compiled,1);assert.equal(c.incrementalCompilation.reusedModules,32);
  assert.deepEqual(c.transpiledBytes,cores[0].transpiledBytes);
});

test('erasing the executing SPM page retires its latched instruction before replacing code',()=>{
  const cores=pair(sequential([[0x95e8],avr.ldi(20,0x5a)]),{...physical,fuseHigh:0xef,nvmClockProfile:1,nvmCalibrationReferenceHz:hz});
  for(const c of cores){c.writeIO(IO.SPMCSR,3);assert.throws(()=>c.runUntilPs(5000000000n),/Unsupported opcode at 0x2/);}
  assert.deepEqual(snapshot(cores[0]),snapshot(cores[1]));
  assert.equal(cores[1].state().cpuPhase.retired,1n);
  assert.equal(cores[1].state().cpuPhase.execPc,1,'Fault belongs to the newly fetched erased word, not the old SPM');
  assert.equal(cores[1].r[20],0);assert.equal(cores[1]._exports.avr_device_generation(),1n);
  assert.equal(cores[1].incrementalCompilation.compiled,1);
});

for(const id of ['rhythmic','lumiere-stereo'])test(`physical audio and active interrupts agree for ${id}`,()=>{
  const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url))),entry=catalog.entries.find(e=>e.id===id);
  const cores=pair(parseHex(entry.flashHex),nominalVerificationDeviceOptions(entry.cpuHz)),channels=entry.audioChannels||1;
  assert.deepEqual(cores[0].capturePhysical(4096,48000,channels),cores[1].capturePhysical(4096,48000,channels));
  same(...cores,id);assert.ok(cores[1].state().irqs>0);assert.deepEqual(cores[0].drainPinsPs(),cores[1].drainPinsPs());
});

test('portable precompiled packages retain their initial module and can select incremental SPM refresh',async()=>{
  const image=selfProgrammingImage(),a=new ATtiny13A(image,null,{fuseHigh:0xef,spmCommandCycles:4});
  const pkg=await createPackage({flash:image,configuration:{fuseHigh:0xef,spmCommandCycles:4},
    runtime:getRuntimeBytes(),translated:a.transpiledBytes,manifest:a.transpilation});
  const b=await ATtiny13A.fromPackage(pkg,{incrementalCompilation:true});assert.equal(b.incrementalCompilation,null);
  for(const core of [a,b])core.runUntil(200000n);same(a,b,'package SPM');assert.equal(b.r[20],0x5a);
  assert.ok(b.incrementalCompilation.reusedModules>0);
  assert.throws(()=>new AVRCore(image,null,{incrementalCompilation:true}),/full ATtiny13A/);
  assert.throws(()=>new ATtiny13A(image,null,{incrementalCompilation:1}),/boolean/);
});
