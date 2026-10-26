import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {generatedFunctions} from './function-names-source.mjs';
const root=fileURLToPath(new URL('../../../',import.meta.url)),dir=fileURLToPath(new URL('./',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex');
const raw=p=>readFileSync(join(dir,p)),read=p=>p.endsWith('.gz')?gunzipSync(raw(p)):raw(p),json=p=>JSON.parse(read(p));
const evidence=json('evidence.json'),gitCache=new Map();
const git=p=>{if(!gitCache.has(p))gitCache.set(p,execFileSync('git',['show',evidence.sourceCommit+':'+p],{cwd:root,maxBuffer:16*1024*1024}));return gitCache.get(p);};
for(const [p,h]of Object.entries(evidence.filesSha256))assert.equal(sha(p.endsWith('.gz')?raw(p):raw(p).toString().replaceAll('\r\n','\n')),h,p);
for(const [archive,path]of [['profile-source.mjs','web-player/scripts/profile-device.mjs'],['function-names-source.mjs','web-player/scripts/lib/avr-profile-functions.mjs'],['analysis-source.mjs','web-player/scripts/analyze-device-profiles.mjs'],['test-source.mjs','web-player/tests/avr-profile-functions.test.mjs']])
  assert.equal(raw(archive).toString().replaceAll('\r\n','\n'),git(path).toString().replaceAll('\r\n','\n'),archive+' source');
assert.match(read('tests.tap.gz').toString(),/# tests 6\r?\n# suites 0\r?\n# pass 6\r?\n# fail 0/);
class Reader{
  constructor(data,start=0){this.data=data;this.at=start;}
  byte(){assert.ok(this.at<this.data.length);return this.data[this.at++];}
  u32(){let n=0,shift=0,b;do{b=this.byte();n+=(b&127)*2**shift;shift+=7;assert.ok(shift<=35);}while(b&128);return n;}
  string(){const length=this.u32(),start=this.at;this.at+=length;assert.ok(this.at<=this.data.length);return this.data.subarray(start,this.at).toString();}
}
function sections(binary){
  assert.ok(binary.subarray(0,8).equals(Buffer.from([0,97,115,109,1,0,0,0])));
  const r=new Reader(binary,8),out=[];
  while(r.at<binary.length){const start=r.at,id=r.byte(),length=r.u32(),payload=r.at,end=payload+length;assert.ok(end<=binary.length);out.push({start,id,payload,end});r.at=end;}
  return out;
}
const executable=b=>Buffer.concat([b.subarray(0,8),...sections(b).filter(s=>s.id!==0).map(s=>b.subarray(s.start,s.end))]);
function layout(binary){
  const imports=[],exports=[],bodies=[];
  for(const s of sections(binary)){
    const r=new Reader(binary,s.payload);
    if(s.id===2)for(let n=r.u32();n;n--){const module=r.string(),name=r.string(),kind=r.byte();if(kind===0){r.u32();imports.push({module,name,index:imports.length});}else{assert.equal(kind,2);const flags=r.u32();r.u32();if(flags&1)r.u32();}}
    if(s.id===7)for(let n=r.u32();n;n--){const name=r.string(),kind=r.byte(),index=r.u32();if(kind===0)exports.push({name,index});}
    if(s.id===10){for(let n=r.u32();n;n--){const offset=r.at,size=r.u32();bodies.push({index:imports.length+bodies.length,offset,codeOffset:r.at,end:r.at+size});r.at+=size;}assert.equal(r.at,s.end);}
  }
  return {imports,exports,bodies};
}
function unnamed(binary){const last=sections(binary).at(-1);assert.equal(last.id,0);assert.equal(new Reader(binary,last.payload).string(),'name');return binary.subarray(0,last.start);}
function names(binary){
  const custom=WebAssembly.Module.customSections(new WebAssembly.Module(binary),'name');assert.equal(custom.length,1);
  const r=new Reader(Buffer.from(custom[0])),map=new Map();
  while(r.at<r.data.length){const id=r.byte(),length=r.u32(),end=r.at+length;if(id===1)for(let n=r.u32();n;n--)map.set(r.u32(),r.string());r.at=end;}
  return map;
}
const native=json('native-functions.json.gz'),nativeBinary=read('native-named.wasm.gz');
const production=git('web-player/wasm/attiny13a.wasm'),nativeNames=names(nativeBinary);
assert.ok(unnamed(nativeBinary).equals(production));assert.equal(native.length,layout(nativeBinary).bodies.length);
for(const f of native)assert.equal(nativeNames.get(f.index),f.name);
const pooled=json('analysis.json.gz');assert.equal(pooled.complete,true);assert.equal(pooled.callTrace,null);assert.equal(pooled.runtimeSha256,sha(production));
const aggregate=new Map(),cases=[];let profiles=0,samples=0;
for(const label of ['music','internal','clki']){
  const summary=json(label+'/summary.json.gz');assert.equal(summary.complete,true);assert.equal(summary.git.head,evidence.sourceCommit);assert.equal(summary.git.status,'');
  assert.equal(summary.parameters.boundedRegions,true);assert.equal(summary.parameters.optimizePhaseLocals,false);assert.equal(summary.parameters.operation,'capture');
  assert.equal(summary.provenance.runtimeSha256,sha(production));assert.equal(summary.provenance.namedRuntimeSha256,sha(nativeBinary));
  assert.equal(summary.provenance.runtimeRebuildByteEqual,true);
  for(const [p,h]of Object.entries(summary.provenance.sourceSha256NormalizedLF))assert.equal(sha(git(p).toString().replaceAll('\r\n','\n')),h,p);
  for(const result of summary.results){
    const binary=read(label+'/'+result.id+'-cpu-named.wasm.gz'),original=unnamed(binary),module=new WebAssembly.Module(binary);
    const manifest=JSON.parse(Buffer.from(WebAssembly.Module.customSections(module,'micromusic.avr')[0]));
    const functions=json(label+'/'+result.id+'-functions.json.gz');
    assert.deepEqual(functions,generatedFunctions({transpilation:manifest},layout(binary)));
    const cpuNames=names(binary);for(const f of functions.functions)assert.equal(cpuNames.get(f.index),f.name);
    assert.equal(sha(binary),result.generatedNamedSha256);assert.equal(sha(original),result.generatedOriginalSha256);assert.equal(sha(executable(binary)),result.generatedExecutableSectionsSha256);
    const known=new Map([...native,...functions.functions].map(f=>[f.name,f]));
    const info=f=>{const plain=f.functionName.replace(/^\$/,'');if(known.has(plain))return{key:plain,category:known.get(plain).category};
      if(f.url?.startsWith('wasm:'))return{key:plain+'@'+f.url,category:'unresolved_wasm'};
      let category='other_js_vm';if(f.functionName==='(garbage collector)')category='v8_gc';else if(f.functionName==='(idle)')category='v8_idle';
      else if(/\/(?:attiny13a-runtime|avr-runtime|avr-transpiled-runtime)\.js$/.test(f.url||''))category='javascript_bridge';
      else if(/profile-device\.mjs$/.test(f.url||'')||f.url?.startsWith('node:inspector'))category='profiler_harness';
      return{key:f.functionName+'@'+f.url+':'+f.lineNumber,category};};
    const combined=new Map(),categoryCounts=new Map();let total=0;
    for(const run of result.runs){
      assert.equal(run.productionEquality,true);assert.equal(run.architectureSha256,result.referenceArchitectureSha256);
      const rawProfile=read(label+'/'+run.profile+'.gz');assert.equal(sha(rawProfile),run.profileSha256);
      const profile=JSON.parse(rawProfile),nodes=new Map(profile.nodes.map(n=>[n.id,n])),parent=new Map();
      for(const n of nodes.values())for(const child of n.children||[])parent.set(child,n.id);
      const counts={all:new Map(),work:new Map()},categories={all:new Map(),work:new Map()};let work=0;
      for(const id of profile.samples){
        const stack=[];for(let at=id;at!==undefined;at=parent.get(at)){assert.ok(nodes.has(at));stack.push(nodes.get(at).callFrame);}
        const selected=stack.some(f=>f.functionName==='capturePhysical'&&/\/attiny13a-runtime\.js$/.test(f.url));if(selected)work++;
        const frames=stack.map(info);
        for(const window of selected?['all','work']:['all']){
          const category=frames[0].category;categories[window].set(category,(categories[window].get(category)||0)+1);
          const seen=new Set();for(const [n,f]of frames.entries()){if(seen.has(f.key))continue;seen.add(f.key);const row=counts[window].get(f.key)||{self:0,inclusive:0};row.inclusive++;if(n===0)row.self++;counts[window].set(f.key,row);}
        }
      }
      assert.equal(profile.samples.length,run.samples);assert.equal(work,run.workStackSamples);assert.equal(work,run.captureStackSamples);
      const deltas=[...profile.timeDeltas].sort((a,b)=>a-b);assert.deepEqual(run.sampleDeltasUs,{min:deltas[0],median:deltas[Math.floor(deltas.length/2)],max:deltas.at(-1)});
      for(const [window,rows,cats,denominator]of [['all',run.allFrames,run.allLeafCategories,run.samples],['work',run.workFrames,run.workLeafCategories,work]]){
        assert.equal(rows.length,counts[window].size);for(const f of rows){const c=counts[window].get(f.key);assert.deepEqual(c,{self:f.selfSamples,inclusive:f.inclusiveSamples});assert.equal(f.selfPercent,100*c.self/denominator);assert.equal(f.inclusivePercent,100*c.inclusive/denominator);assert.equal(f.category,info({functionName:f.name,url:f.url,lineNumber:(f.line??1)-1}).category);}
        assert.equal(cats.length,categories[window].size);for(const c of cats){assert.equal(c.samples,categories[window].get(c.category));assert.equal(c.percent,100*c.samples/denominator);}
      }
      for(const f of run.workFrames){const c=combined.get(f.key)||{self:0,inclusive:0};c.self+=f.selfSamples;c.inclusive+=f.inclusiveSamples;combined.set(f.key,c);}
      for(const c of run.workLeafCategories)categoryCounts.set(c.category,(categoryCounts.get(c.category)||0)+c.samples);
      profiles++;samples+=work;total+=work;
    }
    const row=pooled.results.find(r=>r.id===result.id);assert.ok(row);assert.equal(row.samples,total);assert.equal(row.frames.length,combined.size);
    for(const f of row.frames){assert.deepEqual(combined.get(f.key),{self:f.selfSamples,inclusive:f.inclusiveSamples});assert.equal(f.selfPercent,100*f.selfSamples/total);assert.equal(f.inclusivePercent,100*f.inclusiveSamples/total);}
    for(const c of row.categories){assert.equal(c.samples,categoryCounts.get(c.category));assert.equal(c.percent,100*c.samples/total);}
    aggregate.set(result.id,{samples:total});cases.push({summary,result,manifest,original});
  }
}
assert.equal(profiles,15);assert.equal(pooled.profiles,profiles);assert.equal(pooled.samples,samples);assert.equal(pooled.results.length,cases.length);
if(process.argv.includes('--verify-execution')){
  for(const {summary}of cases)for(const [p,h]of Object.entries(summary.provenance.sourceSha256NormalizedLF).filter(([p])=>p.startsWith('web-player/lib/')))
    assert.equal(sha(readFileSync(join(root,p),'utf8').replaceAll('\r\n','\n')),h,'Execution replay requires pinned library sources: '+p);
  const {ATtiny13A}=await import('../../lib/attiny13a-runtime.js'),{parseHex}=await import('../../lib/hex.js');
  const {avr,IO,flash}=await import('../../tests/fixtures/attiny13a-system-firmware.mjs');
  const catalog=['web-player/firmware.json','web-player/hq4-firmware.json'].flatMap(p=>JSON.parse(git(p)).entries);
  const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
  const stringify=v=>JSON.stringify(v,(_,x)=>typeof x==='bigint'?x.toString():x,2)+'\n';
  for(const {summary,result,manifest,original}of cases){
    const p=summary.parameters,entry=p.kernel?null:catalog.find(e=>e.id===result.id),hz=p.kernel?p.frequency:(entry.cpuHz||9600000);
    const binary=p.kernel?kernel:parseHex(entry.flashHex),eeprom=entry?.eepromHex?parseHex(entry.eepromHex,64):null;
    const options={oscillatorHz:hz,fastIdle:p.fastIdle,optimizeFlags:true,resumable:true,boundedRegions:true,runtimeModule:new WebAssembly.Module(production),precompiled:{bytes:original,manifest}};
    if(p.clock==='clki'){options.fuseLow=0x70;options.clkiProfile={phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1};}
    else{options.osccalHz=Array(128).fill(0);options.osccalHz[0]=hz;if(p.kernel)options.fuseLow=0x72;else{options.nvmClockProfile=1;options.nvmCalibrationReferenceHz=hz;}}
    const core=new ATtiny13A(binary,eeprom,options);assert.equal(sha(binary),result.flashSha256);
    if(p.kernel){core.writeIO(IO.CLKPR,128);core.writeIO(IO.CLKPR,Math.log2(p.divisor));}
    if(p.clock==='clki'){const end=BigInt(p.frames)*1000000000000n/BigInt(p.rate),width=1000000000000n/BigInt(2*hz);assert.equal(core.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:width,lowPs:width,transitionCount:end/width,knownUntilPs:end}),true);}
    else{core.injectPinsPs({at:777777n,mask:4,levels:4});core.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});}
    const pcm=[];for(let at=0;at<p.frames;at+=p.blockFrames){const block=core.capturePhysical(Math.min(p.blockFrames,p.frames-at),p.rate,result.channels);pcm.push(Buffer.from(block.buffer,block.byteOffset,block.byteLength));}
    const observed={state:core.state(),diagnostics:Array.from(core._state),data:core.data.slice(),eeprom:core.eeprom.slice(),flash:core.rom.slice(),irqFrames:Array.from(core.irqFrames),tailPins:core.drainPinsPs()};
    assert.equal(sha(stringify(observed)),result.referenceArchitectureSha256,result.id+' state');
    for(const run of result.runs)assert.equal(sha(Buffer.concat(pcm)),run.rawPcmSha256,result.id+' PCM');
  }
}
console.log(JSON.stringify({profiles,samples,cases:cases.length,runtimeSha256:sha(production),executionVerified:process.argv.includes('--verify-execution')}));
