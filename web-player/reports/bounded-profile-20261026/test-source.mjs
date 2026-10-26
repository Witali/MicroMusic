import {test} from 'node:test';
import assert from 'node:assert/strict';
import {AVRCore} from '../lib/avr-transpiled.js';
import {ATtiny13A} from '../lib/attiny13a.js';
import {avr,flash} from './fixtures/attiny13a-system-firmware.mjs';
import {generatedFunctions} from '../scripts/lib/avr-profile-functions.mjs';

// Independently read the actual export indices and element dispatch targets;
// names must describe what the binary calls, not just its metadata's counts.
function layout(core){
  const bytes=core.transpiledBytes;let at=8;
  const u32=()=>{let value=0,shift=0,b;do{b=bytes[at++];value+=(b&127)*2**shift;shift+=7;}while(b&128);return value;};
  const string=()=>{const n=u32(),s=new TextDecoder().decode(bytes.subarray(at,at+n));at+=n;return s;};
  const imports=WebAssembly.Module.imports(new WebAssembly.Module(bytes)).filter(i=>i.kind==='function');
  const exports=[],bodies=[],table=[];
  while(at<bytes.length){
    const id=bytes[at++],length=u32(),end=at+length;
    if(id===7){for(let n=u32();n;n--){const name=string(),kind=bytes[at++],index=u32();if(kind===0)exports.push({name,index});}}
    if(id===9){assert.equal(u32(),1);assert.equal(u32(),0);assert.equal(bytes[at++],0x41);assert.equal(u32(),0);assert.equal(bytes[at++],0x0b);for(let n=u32();n;n--)table.push(u32());}
    if(id===10){for(let n=u32(),index=imports.length;n;n--,index++){const size=u32();bodies.push({index});at+=size;}}
    at=end;
  }
  return {imports,exports,bodies,table};
}
const image=flash({instructions:[avr.rjmp(0,16)]},
  {at:16,instructions:[avr.inc(16),avr.eor(17,18),avr.rjmp(18,16)]},
  {at:64,instructions:[avr.inc(19),avr.inc(20),avr.rjmp(66,64)]});
const physical={resumable:true,osccalHz:Array(128).fill(9600000)};
for(const boundedRegions of [false,true])for(const optimizePhaseLocals of [false,true])
test(`profile names identify actual bounded dispatch targets (${boundedRegions}, phase locals ${optimizePhaseLocals})`,()=>{
  const core=new ATtiny13A(image,null,{...physical,boundedRegions,optimizePhaseLocals});
  const actual=layout(core),{functions}=generatedFunctions(core,actual),first=actual.imports.length;
  const lookup=index=>functions[index-first],words=core.transpilation.mapping.length;
  assert.equal(functions.filter(f=>f.role==='empty-block').length,1);
  for(const exp of actual.exports)assert.equal(lookup(exp.index).name,'cpu.'+exp.name);
  for(let pc=0;pc<words;pc++)assert.equal(lookup(actual.table[pc]).role,'instruction');
  if(boundedRegions){
    assert.ok(core.transpilation.regions.length>0);assert.ok(core.transpilation.regionFallbacks.length>0);
    for(const region of core.transpilation.regions)for(const pc of region.pcs){
      const fn=lookup(actual.table[words+pc]);
      assert.equal(fn.role,core.transpilation.regionFallbacks.some(f=>f.pc===pc)?'fallback-wrapper':'region-wrapper');
    }
    assert.equal(functions.filter(f=>f.role==='region-body').length,core.transpilation.regions.length);
  }else assert.equal(functions.some(f=>f.role.startsWith('region')),false);
});
test('legacy ATtiny88 profiling geometry is derived from its real binary rather than 512 words',()=>{
  const core=new AVRCore(Uint8Array.of(0,0),null,{target:'attiny88'}),actual=layout(core);
  const {functions}=generatedFunctions(core,actual);
  assert.equal(functions.filter(f=>f.role==='instruction').length,4096);
  assert.equal(functions.find(f=>f.index===actual.table[4095]).name,'cpu.insn_0x1ffe_unsupported');
});
test('profile attribution rejects unknown emitter geometry and corrupted region metadata',()=>{
  const core=new ATtiny13A(image,null,{...physical,boundedRegions:true}),actual=layout(core);
  assert.throws(()=>generatedFunctions(core,{...actual,bodies:actual.bodies.slice(1)}),/function count/);
  const exports=structuredClone(actual.exports);exports.find(e=>e.name==='run').index=actual.imports.length;
  assert.throws(()=>generatedFunctions(core,{...actual,exports}),/export\/order mismatch/);
  const manifest=structuredClone(core.transpilation);manifest.regionFallbacks[0].region=9999;
  assert.throws(()=>generatedFunctions({transpilation:manifest},actual),/Invalid fallback region/);
});
