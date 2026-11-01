import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ATtiny13A,getRuntimeBytes} from '../lib/attiny13a.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {createPackage} from '../lib/attiny13a-package.js';
import {createCachedDeviceCore} from '../lib/avr-persistent-cache.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {makePhaseProbe,phaseTrace,clearPhaseProbe,PHASE_EVENT as E} from './helpers/avr-phase-probe.mjs';

// DS40002198A sections5.66–68/5.114–16: AVRe indirect SRAM access,
// two cycles, no SREG changes; the high pointer byte is unused on ATtiny13A.
const mem=(name,d,s=26,k=1)=>{
  const store=name==='ST'?0x200:0;
  if(k<2)return [0x9000|store|(d<<4)|(s===26?12:s===28?8:0)|(k<0?2:1)];
  if(s===26){assert.equal(k,2);return [0x900c|store|(d<<4)];}
  const q=k-2;return [0x8000|store|(d<<4)|(s===28?8:0)|((q&32)<<8)|((q&24)<<7)|(q&7)];
};
const body=[mem('LD',16),mem('LD',17),mem('ST',16),mem('LD',18,26,-1),mem('ST',17,28,4),mem('LD',19,30,2)];
const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;osccalHz[1]=9000000;
function image(instructions=body){const end=16+instructions.flat().length;
  return flash({instructions:[avr.rjmp(0,16)]},
    ...Array.from({length:9},(_,n)=>({at:n+1,instructions:[avr.rjmp(n+1,64)]})),
    {at:16,instructions:[...instructions,avr.rjmp(end,end)]},{at:64,instructions:[avr.inc(25),avr.reti()]});
}
function make(binary=image(),sramBlocks=true,extra={},probe=false){
  const options={resumable:true,sramBlocks,cacheTranslation:false,osccalHz,oscillatorHz:hz,fuseLow:0x72,fastIdle:false,...extra};
  const c=probe?makePhaseProbe(binary,options):new ATtiny13A(binary,null,options);
  if(!extra.clkiProfile)c.clock(8);c.pc=16;
  for(let n=0;n<32;n++)c.r[n]=(n*37+11)&255;
  for(let n=96;n<160;n++)c.data[n]=(n*29+3)&255;
  for(const s of [26,28,30])c.r[s]=104;
  c.sreg=0x7f;return c;
}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irq:Array.from(c.irqFrames)});
function same(a,b,label){assert.deepEqual(snapshot(a),snapshot(b),label);assert.deepEqual(a.drainPinsPs(),b.drainPinsPs(),label+' pins');}
function oracleUntil(c,end){for(let at=c.state().timePs;at<end;){at=at+10000n<end?at+10000n:end;c.runUntilPs(at);}}

test('SRAM spans actually replace the individual phase calls and retain architectural state',()=>{
  const a=make(image(),true,{},true),b=make(image(),false);clearPhaseProbe(a);
  assert.equal(a.transpilation.blocks.find(x=>x.start===16).sram,true);
  assert.equal(a.run(body.length),body.length);for(let n=0;n<body.length;n++)b.step();same(a,b,'accepted mixed pointer span');
  const calls=phaseTrace(a).filter(e=>e.kind===E.PHASE_ENTER);
  assert.deepEqual(calls.map(e=>e.argument),[24],'one12-cycle clock call');
  assert.equal(phaseTrace(a).filter(e=>[E.READ,E.WRITE,E.LPM].includes(e.kind)).length,0);
});

test('runUntil also executes a whole SRAM span before the strict physical endpoint',()=>{
  const a=make(image(),true,{},true),b=make(image(),false),end=a.state().timePs+1200001n;clearPhaseProbe(a);
  a.runUntilPs(end);oracleUntil(b,end);same(a,b,'bounded accepted span');
  assert.equal(phaseTrace(a).filter(e=>e.kind===E.PHASE_ENTER&&e.argument===24).length,1);
});

test('SRAM spans preserve all SREG values with other compiler policies enabled',()=>{
  for(const optimizePhaseLocals of [false,true])for(const boundedRegions of [false,true])for(const optimizeFlags of [false,true]){
    const extra={optimizePhaseLocals,boundedRegions,optimizeFlags},a=make(image(),true,extra),b=make(image(),false,extra);
    for(let sreg=0;sreg<256;sreg++){
      for(const c of [a,b]){c.pc=16;c.sreg=sreg;c.r[26]=104;c.r[28]=104;c.r[30]=104;}
      assert.equal(a._execute('block',Infinity,64),body.length);
      for(let n=0;n<body.length;n++)b.step();same(a,b,'SREG '+sreg);assert.equal(a.sreg,sreg);
    }
  }
});

test('branch targets split spans and the complete64-byte SRAM span is accepted',()=>{
  const loads=Array.from({length:64},()=>mem('LD',16));
  const full=flash({at:16,instructions:[...loads,avr.rjmp(80,80)]});
  const a=make(full,true,{maxBlockInstructions:64}),b=make(full,false,{maxBlockInstructions:64});
  for(const c of [a,b])c.r[26]=96;
  assert.equal(a._execute('block',Infinity,64),64);for(let n=0;n<64;n++)b.step();same(a,b,'entire SRAM');
  assert.equal(a.r[26],160);
  const binary=flash({instructions:[avr.rjmp(0,17)]},{at:16,instructions:[...body,avr.rjmp(22,22)]});
  const c=make(binary),d=make(binary,false);
  assert.equal(c.transpilation.blocks.some(x=>x.sram&&x.start===16),false);
  assert.ok(c.transpilation.blocks.some(x=>x.sram&&x.start===17));
  c.run(6);for(let n=0;n<6;n++)d.step();same(c,d,'internal entry');
});

for(const s of [26,28,30])for(const k of [-1,1,2,5]){
  if(s===26&&k>2)continue;
  test(`SRAM preflight covers every initial pointer value, s=${s}, k=${k}`,()=>{
    const binary=image([mem('LD',16,s,k),mem('ST',16,s,k)]);
    const a=make(binary),b=make(binary,false);
    for(let pointer=0;pointer<256;pointer++){
      // A rejected preflight must be completely side-effect free, even when
      // the second access would leave SRAM or wrap the low pointer byte.
      for(const c of [a,b]){c.pc=16;c.r[s]=pointer;}
      const before=snapshot(a),n=a._execute('block',Infinity,2);
      if(n){assert.equal(n,2);b.step();b.step();same(a,b,'pointer '+pointer);}
      else assert.deepEqual(snapshot(a),before,'rejected pointer '+pointer);
    }
  });
}

test('ordered store/load dependencies and other pointer register sources are preserved',()=>{
  const binary=image([mem('ST',28,26,2),mem('LD',16,26,2),mem('ST',16,30,2),mem('LD',17,30,2),mem('ST',26,28,1)]);
  const a=make(binary),b=make(binary,false);assert.equal(a._execute('block',Infinity,64),5);
  for(let n=0;n<5;n++)b.step();same(a,b,'sequential effects');assert.equal(a.r[17],104);
});

test('pointer destinations and undefined auto-update aliases stay outside SRAM blocks',()=>{
  for(const op of [mem('LD',26,26,2),mem('LD',28,26,2),mem('LD',27,26,1),mem('ST',26,26,1),mem('ST',27,26,-1)]){
    const binary=image([op,mem('LD',16),mem('LD',17)]),a=make(binary),b=make(binary,false);
    assert.equal(a.transpilation.blocks.some(x=>x.start===16&&x.sram),false);
    assert.equal(a._execute('block',Infinity,64),0);same(a,b,'excluded entry');
    let ae,be;try{a.run(3);}catch(e){ae=e.message;}try{for(let n=0;n<3;n++)b.step();}catch(e){be=e.message;}
    assert.equal(ae,be);same(a,b,'original alias/fault behavior');
  }
});

test('failed later addresses fall back without replaying any successful prefix',()=>{
  const binary=image([mem('ST',16),mem('LD',17),mem('ST',18)]);
  for(const pointer of [0,16,32+IO.PORTB,95,158,159,254,255]){
    const a=make(binary),b=make(binary,false);for(const c of [a,b])c.r[26]=pointer;
    let ae,be;try{a.run(3);}catch(e){ae=e.message;}try{for(let n=0;n<3;n++)b.step();}catch(e){be=e.message;}
    assert.equal(ae,be,'fault pointer '+pointer);same(a,b,'fallback pointer '+pointer);
  }
});

for(const kind of ['deadline','timer','comparator','pin','reset','eeprom-window','watchdog-window','clkpr','osccal'])
test(`SRAM spans retain exact ${kind} observation boundaries`,()=>{
  const binary=image(Array.from({length:20},(_,n)=>mem(n%2?'ST':'LD',16+n%6)));
  const a=make(binary),b=make(binary,false),start=a.state().timePs;
  for(const c of [a,b]){
    if(kind==='timer'){c.writeIO(IO.OCR0A,5);c.writeIO(IO.TIMSK0,4);c.writeIO(IO.TCCR0B,1);c.sreg=128;}
    if(kind==='comparator'){c.writeIO(IO.ACSR,8);c.sreg=128;c.setAnalogPs({at:start+350001n,pin:0,microvolts:2000000});}
    if(kind==='pin'){c.writeIO(IO.PCMSK,1);c.writeIO(IO.GIMSK,0x20);c.sreg=128;c.injectPinsPs({at:start+350001n,mask:1,levels:1});}
    if(kind==='reset')c.injectPinsPs({at:start+350001n,mask:32,levels:0});
    if(kind==='eeprom-window'){c.writeIO(IO.EEARL,3);c.writeIO(IO.EEDR,0x5a);c.writeIO(IO.EECR,4);}
    if(kind==='watchdog-window')c.writeIO(IO.WDTCR,0x18);
    if(kind==='clkpr'){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,3);}
  }
  for(const offset of [199999n,200000n,200001n,350000n,350001n,1100000n,3999999n,4000000n,4000001n,5000001n]){
    const end=start+offset;a.runUntilPs(end);oracleUntil(b,end);same(a,b,kind+' at '+offset);
    if(offset===350001n){
      // Host edits are legal while an individual instruction is paused.
      for(const c of [a,b]){c.data[110]=0x75;c.r[17]=0x8a;c.r[26]=108;c.sreg^=0x7f;if(kind==='osccal')c.writeIO(IO.OSCCAL,1);}
    }
  }
});

test('accepted SRAM blocks retain high retirement bits through the uint64 endpoint',()=>{
  for(const start of [0xfffffffen,0xffffffffffffffffn-6n]){
    const a=make(),b=make(image(),false);
    for(const c of [a,b])new DataView(c._exports.memory.buffer).setBigUint64(c._phaseABI.retired,start,true);
    assert.equal(a._execute('block',Infinity,64),6);for(let n=0;n<6;n++)b.step();same(a,b,'retirement '+start);
    assert.equal(a.state().cpuPhase.retired,start+6n);
  }
});

test('instruction/IRQ/retirement limits reject SRAM blocks before any effect',()=>{
  for(const kind of ['budget','irq-delay','pending-irq','counter']){
    const a=make(),b=make(image(),false);
    for(const c of [a,b]){
      if(kind==='irq-delay')c.irqDelay=1;
      if(kind==='pending-irq'){c.writeIO(IO.EECR,8);c.sreg=128;}
      if(kind==='counter')new DataView(c._exports.memory.buffer).setBigUint64(c._phaseABI.retired,0xfffffffffffffffen,true);
    }
    assert.equal(a._execute('block',Infinity,kind==='budget'?5:64),0);same(a,b,kind);
  }
});

test('CLKI waits keep the original memory bus phases and state during both held levels',()=>{
  for(const initialLevel of [0,1]){
    const extra={fuseLow:0x70,osccalHz:undefined,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel}};
    const a=make(image(),true,extra),b=make(image(),false,extra);
    for(const c of [a,b])c.injectClkiPeriodicPs({startPs:0n,initialLevel,highPs:70000n,lowPs:30000n,transitionCount:19n,knownUntilPs:2000000n});
    assert.equal(a._execute('block',Infinity,64),0);same(a,b,'CLKI entry');
    for(const end of [30000n,70000n,70001n,900000n,950000n,2000000n]){a.runUntilPs(end);oracleUntil(b,end);same(a,b,'CLKI '+end);}
  }
});

test('SRAM policy has distinct in-memory and persistent cache entries',async()=>{
  const rows=new Map(),store={get:k=>rows.get(k),put:(k,v)=>{rows.set(k,v);return true;},delete:k=>rows.delete(k)};
  const options={resumable:true,osccalHz,oscillatorHz:hz,fuseLow:0x72},binary=image(),cores=[];
  for(const sramBlocks of [false,true,false,true])cores.push(await createCachedDeviceCore({Core:ATtiny13A,flash:binary,
    runtimeBytes:getRuntimeBytes(),options:{...options,sramBlocks},store}));
  assert.notEqual(cores[0].persistentTranslationCache.key,cores[1].persistentTranslationCache.key);
  assert.ok(cores[2].persistentTranslationCache.hit);assert.ok(cores[3].persistentTranslationCache.hit);assert.equal(rows.size,2);
  for(let n=0;n<cores.length;n++)assert.equal(cores[n].transpilation.sramBlocks??false,!!(n%2));
  const plain=new ATtiny13A(binary,null,options),optimized=new ATtiny13A(binary,null,{...options,sramBlocks:true});
  assert.notEqual(plain._translatedModule,optimized._translatedModule);
  assert.equal(new ATtiny13A(binary,null,{...options,sramBlocks:true})._translatedModule,optimized._translatedModule);
});

test('packaged SRAM policy survives actual SPM and incremental recompilation; verification disables it',async()=>{
  const write=(io,v)=>[...avr.ldi(16,v),...avr.out(io,16)],target=128;
  // Erase/write the actual target page, replacing two NOPs by an LD X+ chain.
  const newWords=[...mem('LD',20),...mem('LD',21),0xcfff];
  const words=[...avr.ldi(26,96),...avr.ldi(30,0),...avr.ldi(31,1),...write(IO.SPMCSR,3),0x95e8];
  for(const [n,w] of newWords.entries())words.push(...avr.ldi(30,2*n),...avr.ldi(16,w&255),0x2e00,
    ...avr.ldi(16,w>>8),0x2e10,...write(IO.SPMCSR,1),0x95e8);
  words.push(...avr.ldi(30,0),...write(IO.SPMCSR,5),0x95e8,avr.rjmp(words.length+4,target)[0]);
  const binary=flash({instructions:[words]},{at:target,instructions:[[0,0,0xcfff]]});
  const configuration={oscillatorHz:hz,osccalHz,fuseLow:0x72,resumable:true,fuseHigh:0xef,spmCommandCycles:4,
    nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
  const probe=new ATtiny13A(binary,null,configuration),generated=transpileAVR(binary,runtimeABI(probe._exports,{resumable:true}),{resumable:true,sramBlocks:true});
  const pkg=await createPackage({flash:binary,configuration,runtime:getRuntimeBytes(),translated:generated.bytes});
  const cores=[];
  for(const incrementalCompilation of [false,true]){
    const c=await ATtiny13A.fromPackage(pkg,{incrementalCompilation});cores.push(c);
    c.data[96]=0x5a;c.data[97]=0xa5;c.runUntilPs(20000000000n);
    assert.equal(c._exports.avr_device_generation(),2n);assert.equal(c.transpilation.sramBlocks,true);
    assert.ok(c.transpilation.blocks.some(b=>b.start===target&&b.sram));assert.equal(c.r[20],0x5a);assert.equal(c.r[21],0xa5);
    assert.equal(c.state().deviceFault,0);
  }
  same(...cores,'monolithic/incremental SPM');
  const verification=await ATtiny13A.fromPackage(pkg,{verification:true});
  assert.equal(verification.transpilation.sramBlocks,undefined);assert.equal(verification._translationOptions.sramBlocks,false);
});

test('SRAM blocks reject invalid options and nonresumable execution',()=>{
  for(const value of [1,null,'true'])assert.throws(()=>make(image(),value),/SRAM blocks/);
  assert.throws(()=>new ATtiny13A(image(),null,{sramBlocks:true}),/resumable/);
});
