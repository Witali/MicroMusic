import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ATtiny13A} from '../lib/attiny13a.js';
import {transpileAVR} from '../lib/avr-transpiler.js';
import {avr,IO,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {rr} from './helpers/avr-test-state.mjs';

const hz=10000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
const options={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0xf2,fastIdle:false,optimizeFlags:false};
const neutral=flash({instructions:[avr.nop(),avr.ldi(16,0xab),[rr(0x2c00,17,16)],
  [0x0198],[0x9542],avr.rjmp(5,0)]}); // MOVW r18,r16; SWAP r20.
const make=(image=neutral,extra={})=>{
  const c=new ATtiny13A(image,null,{...options,boundedRegions:true,...extra});c.clock(8);c.pc=0;return c;
};
const pair=(image=neutral,extra={})=>[true,false].map(boundedRegions=>make(image,{...extra,boundedRegions}));
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),
  eeprom:c.eeprom.slice(),flash:c.rom.slice(),irq:Array.from(c.irqFrames)});
const same=(a,b,label)=>{assert.deepEqual(snapshot(a),snapshot(b),label);assert.equal(a.state().deviceFault,0);};
const step=(c,n)=>{for(let i=0;i<n;i++)c.step();};
function initialize(c,flags){
  c._call('avr_reset',0,0);c.clock(8);c.pc=0;c.sreg=flags;
  for(let n=0;n<32;n++)c.r[n]=(flags+n*17)&255;
}
function functionBodies(bytes){
  let p=8;const u32=()=>{let n=0;for(let shift=0;shift<35;shift+=7){const b=bytes[p++];n+=(b&127)*2**shift;if(!(b&128))return n;}throw Error('Invalid test WASM');};
  while(p<bytes.length){const id=bytes[p++],size=u32(),end=p+size;
    if(id===10){const count=u32();return Array.from({length:count},()=>{const size=u32(),body=Buffer.from(bytes.subarray(p,p+size));p+=size;return body;});}
    p=end;
  }
  throw Error('Missing code section');
}
function addressBytes(value){const out=[0x41];let more;
  do{const b=value&127;value>>=7;more=!((value===0&&!(b&64))||(value===-1&&(b&64)));out.push(b|(more?128:0));}while(more);
  return out;
}
const references=(body,needle)=>{let count=0;for(let at=0;(at=body.indexOf(needle,at))>=0;at+=needle.length)count++;return count;};
function traffic(bytes,manifest){
  const bodies=functionBodies(bytes),address=addressBytes(manifest.abi.data+IO.SREG+32);
  const load=Buffer.from([...address,0x2d,0,0]),save=Buffer.from([...load,0x21,7]);
  const restore=Buffer.from([...address,0x20,7,0x3a,0,0]);
  return {bodies:manifest.regions.map((_,n)=>bodies[manifest.mapping.length+manifest.stats.blocks+n]),load,save,restore};
}

// Exercise the emitter's backward-compatible default without retaining a copied
// optimizer or baseline binary: only omit the new internal dependency hint.
const sourceURL=new URL('../lib/avr-transpiler.js',import.meta.url);
const regionURL=new URL('../lib/avr-wasm-regions.js',import.meta.url).href;
const oldRegions='data:text/javascript;base64,'+Buffer.from(
  `import {planRegions,emitRegion as emit} from ${JSON.stringify(regionURL)};\n`+
  'export {planRegions}; export const emitRegion=(region,{touchesFlags,...options})=>emit(region,options);').toString('base64');
const conservativeSource=readFileSync(sourceURL,'utf8').replace(/from '([^']+)'/g,(_,path)=>
  'from '+JSON.stringify(path==='./avr-wasm-regions.js'?oldRegions:new URL(path,sourceURL).href));
const {transpileAVR:conservativeTranspile}=await import('data:text/javascript;base64,'+Buffer.from(conservativeSource).toString('base64'));
const translate=(fn,image,c,boundedRegions=true)=>fn(image,c.transpilation.abi,
  {resumable:true,boundedRegions,optimizeFlags:false,optimizePhaseLocals:c.transpilation.optimizePhaseLocals===true});

test('neutral regions remove exactly one SREG load/store pair and retain the IRQ read',()=>{
  for(const optimizePhaseLocals of [false,true]){
    const c=make(neutral,{optimizePhaseLocals});
    const after=translate(transpileAVR,neutral,c),before=translate(conservativeTranspile,neutral,c);
    assert.equal(after.manifest.regions.length,1);assert.ok(WebAssembly.validate(after.bytes));
    const a=traffic(after.bytes,after.manifest),b=traffic(before.bytes,before.manifest);
    assert.equal(references(b.bodies[0],b.load),2);assert.equal(references(b.bodies[0],b.restore),1);
    assert.equal(references(a.bodies[0],a.load),1,'pending enabled IRQ still reads current I');
    assert.equal(references(a.bodies[0],a.save),0);assert.equal(references(a.bodies[0],a.restore),0);
    const reduced=Buffer.from(b.bodies[0].toString('hex').replace(b.save.toString('hex'),'').replace(b.restore.toString('hex'),''),'hex');
    assert.deepEqual(a.bodies[0],reduced,'all other region opcodes are byte-identical');
    assert.equal(b.bodies[0].length-a.bodies[0].length,b.save.length+b.restore.length);
    assert.deepEqual(translate(transpileAVR,neutral,c,false).bytes,translate(conservativeTranspile,neutral,c,false).bytes,
      'boundedRegions:false output is unchanged');
  }
});

test('every incoming SREG value survives actual neutral batches in both local policies',()=>{
  for(const optimizePhaseLocals of [false,true]){
    const [a,b]=pair(neutral,{optimizePhaseLocals});
    for(let flags=0;flags<256;flags++){
      for(const c of [a,b])initialize(c,flags);
      assert.equal(a._execute('block',Infinity,64),32);step(b,32);same(a,b,'SREG '+flags);
      assert.equal(a.sreg,flags);assert.equal(a.state().cpuPhase.retired,32n);
    }
  }
});

test('flag-free CPSE/SBRC/SBRS retain two-word skips, path cycles and early bus exits',()=>{
  for(const kind of ['CPSE','SBRC','SBRS'])for(const skip of [false,true]){
    const control=kind==='CPSE'?rr(0x1000,0,1):0xfc00|(kind==='SBRS'?512:0);
    const image=flash({instructions:[[control],avr.lds(17,0x60),avr.ldi(16,42),avr.rjmp(4,0)]});
    for(const flags of [0,0x73,0x80,0xff]){
      const [a,b]=pair(image);
      for(const c of [a,b]){c.sreg=flags;c.r[0]=kind==='CPSE'?1:kind==='SBRS'?Number(skip):Number(!skip);
        c.r[1]=skip?1:0;c.data[0x60]=0x5a;}
      const count=skip?32:1;assert.equal(a._execute('block',Infinity,64),count);step(b,count);same(a,b,kind+' skip '+skip);
      assert.equal(a.sreg,flags);assert.equal(a.pc,skip?4:1);
      assert.equal(a.run(4),4);step(b,4);same(a,b,kind+' fallback');
      const t=traffic(a.transpiledBytes,a.transpilation);
      assert.equal(references(t.bodies[0],t.load),1);assert.equal(references(t.bodies[0],t.restore),0);
    }
  }
});

test('public register and SREG edits are reread between neutral region entries',()=>{
  for(const optimizePhaseLocals of [false,true]){
    const [a,b]=pair(neutral,{optimizePhaseLocals});
    for(const flags of [0,1,0x40,0x73,0x80,0xff,0x12]){
      for(const c of [a,b]){c.pc=0;c.sreg=flags;c.r[20]=flags^0xa5;}
      assert.equal(a._execute('block',Infinity,64),32);step(b,32);same(a,b,'edited SREG '+flags);
      assert.equal(a.sreg,flags);
    }
  }
});

test('neutral region pending-I guard, delayed IRQ and continuations still reject before work',()=>{
  for(const mode of ['irq','delay','active']){
    const [a,b]=pair();
    for(const c of [a,b]){
      c.sreg=0x80;
      if(mode==='irq')c.writeIO(IO.EECR,8);
      if(mode==='delay')c.irqDelay=1;
      if(mode==='active')c.runUntilPs(c.state().timePs+1n);
    }
    const before=snapshot(a);assert.equal(a._execute('block',Infinity,64),0,mode);
    assert.deepEqual(snapshot(a),before,mode+' has no staged effects');same(a,b,mode);
  }
  const [a,b]=pair();for(const c of [a,b]){c.writeIO(IO.EECR,8);c.sreg=0x73;}
  assert.equal(a._execute('block',Infinity,64),32);step(b,32);same(a,b,'pending but I clear');
  a.sreg=b.sreg=0x80;assert.equal(a._execute('block',Infinity,64),0);same(a,b,'public I enable');
});

test('neutral regions preserve strict adjacent deadlines and RESET cancellation',()=>{
  for(const [span,count]of [[399999n,0],[400000n,0],[400001n,2],[6400000n,31],[6400001n,32]]){
    const [a,b]=pair();for(const c of [a,b])c.sreg=0x73;
    const start=a.state().timePs;assert.equal(a._execute('block',Number(start+span),64),count,'span '+span);
    step(b,count);same(a,b,'deadline '+span);if(count)assert.ok(a.state().timePs<start+span);
  }
  const [a,b]=pair();const start=a.state().timePs;
  for(const c of [a,b]){c.sreg=0x73;c.r[16]=17;c.injectPinsPs({at:start+350001n,mask:32,levels:0});}
  assert.equal(a._execute('block',Infinity,64),0);same(a,b,'reset rejects unsafe batch');
  for(const offset of [1n,100000n,350000n,350001n,500001n]){
    if(offset===1n){a.runUntilPs(start+offset);b.runUntilPs(start+offset);a.sreg=b.sreg=0x65;}
    else{a.runUntilPs(start+offset);b.runUntilPs(start+offset);}
    same(a,b,'reset boundary '+offset);assert.deepEqual(a.drainPinsPs(),b.drainPinsPs());
  }
  assert.equal(a.state().resetCount,1);assert.equal(a.state().resetHeld,true);assert.equal(a.sreg,0);
});

test('BRANCH, BLD and flag writers retain the complete conservative region bytecode',()=>{
  for(const [name,operation]of [['INC',avr.inc(16)],['BST',[0xfb00]],['BLD',[0xf900]],
    ['ADC',[rr(0x1c00,16,17)]],['BRANCH',[0xf409]]]){
    // BRNE +1 at PC0 has both paths in this SCC, including the neutral LDI.
    const image=flash({instructions:[operation,avr.ldi(18,42),avr.rjmp(2,0)]}),c=make(image);
    const after=translate(transpileAVR,image,c),before=translate(conservativeTranspile,image,c);
    assert.equal(after.manifest.regions.length,1,name);assert.deepEqual(after.bytes,before.bytes,name);
    const t=traffic(after.bytes,after.manifest);assert.equal(references(t.bodies[0],t.load),2,name);
    assert.equal(references(t.bodies[0],t.save),1,name);assert.equal(references(t.bodies[0],t.restore),1,name);
    const [a,b]=pair(image);for(const flags of [0,0x40,0x73,0xff]){
      for(const core of [a,b])initialize(core,flags);
      assert.equal(a._execute('block',Infinity,64),32);step(b,32);same(a,b,name+' flags '+flags);
    }
  }
});
