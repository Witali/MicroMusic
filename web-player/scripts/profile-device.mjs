// Sampling-only diagnostics. Production sources/artifacts are read, never edited.
import assert from 'node:assert/strict';
import {Session} from 'node:inspector/promises';
import {createHash} from 'node:crypto';
import {execFileSync,spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {cpus,platform,release,arch} from 'node:os';
import {basename,dirname,join,parse,resolve,relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {parseHex} from '../lib/hex.js';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{frames:{type:'string',default:'48000'},
  rate:{type:'string',default:'48000'},repeats:{type:'string',default:'3'},
  'interval-us':{type:'string',default:'1000'},firmware:{type:'string',multiple:true},
  'out-dir':{type:'string',default:'build/profiles/device'},emsdk:{type:'string'},
  help:{type:'boolean'}}});
if(values.help){console.log('node web-player/scripts/profile-device.mjs [--frames 48000] [--rate 48000] [--repeats 3] [--interval-us 1000] [--firmware id,id] [--out-dir build/profiles/device] [--emsdk path]');process.exit(0);}
function integer(value,name,low,high){const n=Number(value);assert.ok(Number.isInteger(n)&&n>=low&&n<=high,`${name}: integer ${low}..${high} required`);return n;}
const frames=integer(values.frames,'frames',1,1048576),rate=integer(values.rate,'rate',8000,192000);
const repeats=integer(values.repeats,'repeats',1,16),intervalUs=integer(values['interval-us'],'interval-us',100,100000);
const blockFrames=1024,out=resolve(root,values['out-dir']);mkdirSync(out,{recursive:true});
const read=path=>readFileSync(resolve(root,path));
const source=path=>read(path).toString('utf8').replaceAll('\r\n','\n');
const hash=value=>createHash('sha256').update(value).digest('hex');
const json=path=>JSON.parse(read(path));
const bytes=array=>Buffer.from(array.buffer,array.byteOffset,array.byteLength);
const stringify=value=>JSON.stringify(value,(_,v)=>typeof v==='bigint'?v.toString():v,2)+'\n';
const save=(path,value)=>writeFileSync(join(out,path),stringify(value));
const git=args=>execFileSync('git',args,{cwd:root,encoding:'utf8'}).trim();
const manifest=json('web-player/wasm/device-build.json'),production=read('web-player/wasm/attiny13a.wasm');
assert.equal(hash(production),manifest.artifacts['attiny13a.wasm'],'Runtime hash mismatch');
for(const [path,expected] of Object.entries(manifest.inputs))assert.equal(hash(source(path)),expected,`Stale runtime: ${path}`);

class Reader{
  constructor(data,start=0,end=data.length){this.data=data;this.at=start;this.end=end;}
  u8(){assert.ok(this.at<this.end,'Truncated WASM');return this.data[this.at++];}
  u32(){let n=0,shift=0,b;do{b=this.u8();n+=(b&127)*2**shift;shift+=7;assert.ok(shift<=35);}while(b&128);return n;}
  string(){const n=this.u32(),start=this.at;this.at+=n;assert.ok(this.at<=this.end);return this.data.subarray(start,start+n).toString('utf8');}
}
function sections(binary){
  assert.ok(binary.subarray(0,8).equals(Buffer.from([0,97,115,109,1,0,0,0])));
  const r=new Reader(binary,8),result=[];
  while(r.at<r.end){const start=r.at,id=r.u8(),size=r.u32(),payload=r.at;r.at+=size;assert.ok(r.at<=r.end);result.push({id,start,payload,end:r.at});}
  return result;
}
function wasmLayout(binary){
  const imports=[],exports=[],bodies=[];
  for(const section of sections(binary)){
    const r=new Reader(binary,section.payload,section.end);
    if(section.id===2){
      const count=r.u32();for(let n=0;n<count;n++){
        const module=r.string(),name=r.string(),kind=r.u8();
        if(kind===0){r.u32();imports.push({module,name,index:imports.length});}
        else if(kind===2){const flags=r.u32();r.u32();if(flags&1)r.u32();}
        else throw Error('Unexpected diagnostic import kind '+kind);
      }
    }else if(section.id===7){
      const count=r.u32();for(let n=0;n<count;n++){const name=r.string(),kind=r.u8(),index=r.u32();if(kind===0)exports.push({name,index});}
    }else if(section.id===10){
      const count=r.u32();for(let n=0;n<count;n++){
        const offset=r.at,size=r.u32();bodies.push({index:imports.length+n,offset,codeOffset:r.at,end:r.at+size});r.at+=size;
      }
      assert.equal(r.at,r.end);
    }
  }
  return {imports,exports,bodies};
}
const uleb=value=>{const out=[];do{let b=value&127;value=Math.floor(value/128);out.push(b|(value?128:0));}while(value);return out;};
const str=value=>{const encoded=Buffer.from(value);return [...uleb(encoded.length),...encoded];};
function named(binary,moduleName,functions){
  const entries=[...uleb(functions.length),...functions.flatMap(fn=>[...uleb(fn.index),...str(fn.name)])];
  const module=[...str(moduleName)],payload=[...str('name'),0,...uleb(module.length),...module,1,...uleb(entries.length),...entries];
  const output=Buffer.concat([binary,Buffer.from([0,...uleb(payload.length),...payload])]);
  assert.ok(executable(output).equals(executable(binary)),'Diagnostic naming changed executable sections');
  return output;
}
function executable(binary){return Buffer.concat([binary.subarray(0,8),...sections(binary).filter(s=>s.id!==0).map(s=>binary.subarray(s.start,s.end))]);}
function runtimeCategory(owner,symbol){
  if(owner==='device')return ['capture_pins','pin_voltages','timer_outputs'].includes(symbol)?'native_pin_body':'native_board_body';
  if(owner==='avr')return /audio_(?:collect|deadline|sample|config|begin|end)/.test(symbol)?'native_audio_body':'native_bridge_body';
  if(owner==='timer0')return 'native_timer0_body';
  if(owner==='system_gpio')return 'native_gpio_body';
  if(owner.startsWith('analog'))return 'native_analog_body';
  if(/system_(watchdog|sleep)|nvm/.test(owner))return 'native_other_peripheral_body';
  return 'native_support_body';
}
let sdk=values.emsdk||process.env.EMSDK;
for(let parent=root;!sdk;parent=dirname(parent)){
  const candidate=join(parent,'build/toolchains/emscripten-6.0.12');
  if(existsSync(join(candidate,'upstream/bin/clang.exe')))sdk=candidate;
  if(parent===parse(parent).root)break;
}
assert.ok(sdk,'Pass --emsdk pointing at the prepared build SDK');sdk=resolve(sdk);
const rebuilt=join(out,'runtime-preopt.wasm'),symbolic=join(out,'runtime-symbols.wasm'),mapPath=join(out,'runtime-link.map');
const compiler=join(sdk,'upstream/bin',process.platform==='win32'?'clang.exe':'clang');
const compileArgs=[...manifest.flags.map(flag=>flag.replaceAll('<emsdk>',sdk)),'--no-wasm-opt',`-Wl,-Map=${mapPath}`,
  ...manifest.sources,'-lc','-lclang_rt.builtins','-o',rebuilt];
const compiled=spawnSync(compiler,compileArgs,{cwd:root,encoding:'utf8'});
if(compiled.error)throw compiled.error;assert.equal(compiled.status,0,compiled.stderr);
// This SDK's clang driver normally invokes wasm-opt -O3 after linking. Run the
// same pass explicitly, printing its final index/name map before names disappear.
const optimizer=join(sdk,'upstream/bin',process.platform==='win32'?'wasm-opt.exe':'wasm-opt');
const optimizeArgs=[rebuilt,'-O3','--print-function-map','-o',symbolic];
const optimized=spawnSync(optimizer,optimizeArgs,{cwd:root,encoding:'utf8'});
if(optimized.error)throw optimized.error;assert.equal(optimized.status,0,optimized.stderr);
const symbolsBinary=readFileSync(symbolic);
assert.ok(symbolsBinary.equals(production),'Same-O3 symbol-map rebuild differs from production');
writeFileSync(join(out,'runtime-optimized.map'),optimized.stdout);
const originalNames=new Map(optimized.stdout.split(/\r?\n/).filter(line=>/^\d+:/.test(line)).map(line=>{
  const colon=line.indexOf(':');return [Number(line.slice(0,colon)),line.slice(colon+1)];
}));
const runtimeLayout=wasmLayout(production),symbols=new Map();
const owners=manifest.sources.map(path=>basename(path,'.c'));
let object='unknown';
for(const line of readFileSync(mapPath,'utf8').split(/\r?\n/)){
  const input=line.match(/^\s+-\s+[0-9a-f]+\s+[0-9a-f]+\s+(.+):\(([^)]+)\)$/i);
  if(input)object=input[1];
  const match=line.match(/^\s+-\s+([0-9a-f]+)\s+([0-9a-f]+)\s+([A-Za-z_$][A-Za-z0-9_.$]*)\s*$/i);
  if(match)symbols.set(match[3],{symbol:match[3],object});
}
const runtimeFunctions=runtimeLayout.bodies.map(body=>{
  const name=originalNames.get(body.index);assert.ok(name,`Missing optimized function name at ${body.index}`);
  const symbol=symbols.get(name)||{symbol:name,object:'optimizer-generated'};
  const owner=owners.find(name=>new RegExp(`(?:^|[/\\\\])${name}(?:-[0-9a-f]+)?\\.o$`,'i').test(symbol.object))||'support';
  return {...body,...symbol,owner,name:`native.${owner}.${symbol.symbol}`,category:runtimeCategory(owner,symbol.symbol)};
});
for(const exp of runtimeLayout.exports)assert.ok(runtimeFunctions.some(fn=>fn.index===exp.index&&(fn.symbol===exp.name||originalNames.get(exp.index)===exp.name)),`Export/name mismatch: ${exp.name}`);
const namedRuntime=named(production,'micromusic.profile.native',runtimeFunctions);
writeFileSync(join(out,'runtime-named.wasm'),namedRuntime);
const runtimeModule=new WebAssembly.Module(namedRuntime),productionModule=new WebAssembly.Module(production);
assert.deepEqual(WebAssembly.Module.imports(runtimeModule),[]);
const catalog=['web-player/firmware.json','web-player/hq4-firmware.json'].flatMap(path=>json(path).entries);
const ids=values.firmware?.flatMap(value=>value.split(',').filter(Boolean))||['rhythmic','lumiere-stereo','hq4-chego-auto'];
assert.ok(ids.length,'Select at least one firmware');assert.equal(new Set(ids).size,ids.length,'Duplicate firmware');
const selected=ids.map(id=>{const entry=catalog.find(item=>item.id===id);assert.ok(entry,'Unknown firmware '+id);return entry;});
const sourcePaths=[...Object.keys(manifest.inputs),'web-player/lib/avr-transpiler.js',
  'web-player/lib/avr-transpiled-runtime.js','web-player/lib/avr-runtime.js',
  'web-player/lib/attiny13a-runtime.js','web-player/lib/hex.js','web-player/scripts/profile-device.mjs'];
const report={schema:'micromusic-device-sampling-profile-v1',createdAt:new Date().toISOString(),
  git:{head:git(['rev-parse','HEAD']),status:git(['status','--short'])},
  node:{version:process.version,versions:process.versions,flags:process.execArgv,executable:process.execPath},
  host:{platform:platform(),release:release(),arch:arch(),cpu:cpus()[0]?.model,logicalCpus:cpus().length},
  parameters:{frames,rate,repeats,intervalUs,blockFrames,fastIdle:true,optimizeFlags:true,firmwareOrder:ids},
  provenance:{runtimeSha256:hash(production),namedRuntimeSha256:hash(namedRuntime),
    executableSectionsSha256:hash(executable(production)),runtimeRebuildByteEqual:true,
    diagnosticCompiler:compiler,compilerVersion:manifest.compilerVersion,compileArgs,optimizer,optimizeArgs,
    sourceSha256NormalizedLF:Object.fromEntries(sourcePaths.map(path=>[path,hash(source(path))]))},
  methodology:{sampling:'Node inspector CPU profiler, no instruction/event callbacks or production instrumentation. Profiles run sequentially; construction, lowering, warmup, comparison, hashing and profile serialization are outside the capture window.',
    naming:'Clang -O3 link followed by the same wasm-opt -O3 pass with --print-function-map gives the optimized function name/index mapping. The link map supplies source-object ownership only. The rebuilt runtime must match every production byte. Diagnostic names are attached to that production binary in a custom name section; all executable sections remain identical. Generated instruction/block/driver names follow existing manifest mapping, block order and exports.',
    attribution:'Self/leaf sample counts are observations, not exact exclusive times. Inclusive samples count ancestors and overlap; do not sum them. O3/V8 inlining attributes inlined work to the surviving containing frame. Body categories describe function ownership, not pure subsystem cost. Native bridge bodies may include inlined pin/audio/clock work.',
    window:'captureStackSamples retain samples with capturePhysical from attiny13a-runtime.js in their recorded ancestors. GC/VM samples may lack this ancestry; total-profile categories remain available. Requested interval is not guaranteed; actual deltas/gaps are retained in raw profiles.',
    limits:'Single Node host, profiler overhead and tiering, no affinity/GC/frequency control. No parallel benchmark is launched by this script. OS/other application load is uncontrolled. Sampling resolves likely hotspots, not causal speedup, exact call counts or browser AudioWorklet latency.'},results:[]};
save('runtime-functions.json',runtimeFunctions);
function generatedFunctions(core){
  const layout=wasmLayout(Buffer.from(core.transpiledBytes)),first=layout.imports.length;
  const mapping=new Map(core.transpilation.mapping.map(instruction=>[instruction.pc,instruction]));
  const functions=layout.bodies.map(body=>{
    const local=body.index-first;let name;
    if(local<512){const i=mapping.get(local);name=`cpu.insn_0x${(local*2).toString(16).padStart(4,'0')}_${i?.name||'continuation'}`;}
    else if(local<512+core.transpilation.blocks.length){const block=core.transpilation.blocks[local-512];name=`cpu.block_0x${(block.start*2).toString(16).padStart(4,'0')}`;}
    else name='cpu.'+(layout.exports.find(exp=>exp.index===body.index)?.name||'emptyBlock');
    return {...body,name,category:'generated_cpu_body'};
  });
  return {layout,functions};
}
function snapshot(core){
  return {state:core.state(),data:core.data.slice(),eeprom:core.eeprom.slice(),flash:core.rom.slice(),irqFrames:Array.from(core.irqFrames)};
}
function capture(core,entry){
  const blocks=[],channels=entry.audioChannels||1;
  for(let offset=0;offset<frames;offset+=blockFrames)blocks.push(core.capturePhysical(Math.min(blockFrames,frames-offset),rate,channels));
  return blocks;
}
function combined(blocks){return Buffer.concat(blocks.map(bytes));}
const known=new Map(runtimeFunctions.map(fn=>[fn.name,fn]));
function frameInfo(frame){
  const plain=frame.functionName.replace(/^\$/,'');
  if(known.has(plain))return {key:plain,name:plain,category:known.get(plain).category,url:frame.url};
  if(frame.url?.startsWith('wasm:'))return {key:plain+'@'+frame.url,name:plain,category:'unresolved_wasm',url:frame.url};
  let category='other_js_vm';
  if(frame.functionName==='(garbage collector)')category='v8_gc';
  else if(frame.functionName==='(idle)')category='v8_idle';
  else if(/\/(?:attiny13a-runtime|avr-runtime|avr-transpiled-runtime)\.js$/.test(frame.url||''))category='javascript_bridge';
  else if(/profile-device\.mjs$/.test(frame.url||'')||frame.url?.startsWith('node:inspector'))category='profiler_harness';
  return {key:frame.functionName+'@'+frame.url+':'+frame.lineNumber,name:frame.functionName||'(anonymous)',category,url:frame.url,line:frame.lineNumber+1};
}
function summarize(profile){
  const nodes=new Map(profile.nodes.map(node=>[node.id,node])),parent=new Map();
  for(const node of profile.nodes)for(const child of node.children||[])parent.set(child,node.id);
  const totals={all:new Map(),capture:new Map()},categories={all:new Map(),capture:new Map()};
  let captureStackSamples=0;
  for(const id of profile.samples||[]){
    const stack=[];for(let at=id;at!==undefined;at=parent.get(at)){const node=nodes.get(at);assert.ok(node);stack.push(frameInfo(node.callFrame));}
    const inCapture=stack.some(frame=>frame.name==='capturePhysical'&&/\/attiny13a-runtime\.js$/.test(frame.url));
    if(inCapture)captureStackSamples++;
    for(const window of inCapture?['all','capture']:['all']){
      const leaf=stack[0];categories[window].set(leaf.category,(categories[window].get(leaf.category)||0)+1);
      const seen=new Set();
      for(const [n,frame] of stack.entries()){
        if(seen.has(frame.key))continue;seen.add(frame.key);
        if(!totals[window].has(frame.key))totals[window].set(frame.key,{...frame,selfSamples:0,inclusiveSamples:0});
        const row=totals[window].get(frame.key);row.inclusiveSamples++;if(n===0)row.selfSamples++;
      }
    }
  }
  const count=profile.samples?.length||0;
  const sorted=(map,n)=>[...map.values()].map(row=>({...row,selfPercent:100*row.selfSamples/n,inclusivePercent:100*row.inclusiveSamples/n})).sort((a,b)=>b.selfSamples-a.selfSamples||b.inclusiveSamples-a.inclusiveSamples);
  const categoryRows=(map,n)=>[...map].map(([category,samples])=>({category,samples,percent:100*samples/n})).sort((a,b)=>b.samples-a.samples);
  const deltas=[...(profile.timeDeltas||[])].sort((a,b)=>a-b);
  return {profileDurationMs:(profile.endTime-profile.startTime)/1000,samples:count,captureStackSamples,
    sampleDeltasUs:{min:deltas[0],median:deltas[Math.floor(deltas.length/2)],max:deltas.at(-1)},
    allLeafCategories:categoryRows(categories.all,count),captureLeafCategories:categoryRows(categories.capture,captureStackSamples),
    allFrames:sorted(totals.all,count),captureFrames:sorted(totals.capture,captureStackSamples)};
}
for(const entry of selected){
  console.log(`Profile ${entry.id}: ${frames} frames @ ${rate} Hz, ${repeats} sequential profiles`);
  const binary=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):null;
  assert.equal(hash(binary),entry.flashSha256);
  const options={oscillatorHz:entry.cpuHz||9600000,fastIdle:true,optimizeFlags:true,runtimeModule};
  const seed=new ATtiny13A(binary,eeprom,options),generated=generatedFunctions(seed);
  for(const fn of generated.functions)known.set(fn.name,fn);
  const namedCpu=named(Buffer.from(seed.transpiledBytes),`micromusic.profile.cpu.${entry.id}`,generated.functions);
  writeFileSync(join(out,entry.id+'-cpu-named.wasm'),namedCpu);save(entry.id+'-functions.json',generated);
  const make=()=>new ATtiny13A(binary,eeprom,{...options,precompiled:{bytes:namedCpu,manifest:seed.transpilation}});
  const reference=new ATtiny13A(binary,eeprom,{...options,runtimeModule:productionModule});
  const expected=combined(capture(reference,entry)),expectedState=snapshot(reference);
  capture(make(),entry); // Unprofiled named-module warmup, same interval.
  const result={id:entry.id,channels:entry.audioChannels||1,flashSha256:hash(binary),
    generatedOriginalSha256:hash(seed.transpiledBytes),generatedNamedSha256:hash(namedCpu),
    generatedExecutableSectionsSha256:hash(executable(Buffer.from(seed.transpiledBytes))),runs:[]};
  for(let repeat=0;repeat<repeats;repeat++){
    const core=make(),session=new Session();session.connect();let profile,blocks,elapsed;
    try{
      await session.post('Profiler.enable');await session.post('Profiler.setSamplingInterval',{interval:intervalUs});
      await session.post('Profiler.start');const started=performance.now();blocks=capture(core,entry);elapsed=performance.now()-started;
      ({profile}=await session.post('Profiler.stop'));
    }finally{session.disconnect();}
    const raw=combined(blocks);assert.ok(raw.equals(expected),entry.id+' named/profiled PCM differs from production');
    assert.deepEqual(snapshot(core),expectedState,entry.id+' named/profiled architecture differs from production');
    const rawName=`${entry.id}-${repeat}.cpuprofile`;save(rawName,profile);
    result.runs.push({repeat,profile:rawName,profileSha256:hash(readFileSync(join(out,rawName))),captureWallMs:elapsed,
      rawPcmSha256:hash(raw),architectureSha256:hash(stringify(snapshot(core))),productionEquality:true,...summarize(profile)});
  }
  report.results.push(result);report.complete=report.results.length===selected.length;report.updatedAt=new Date().toISOString();save('summary.json',report);
  console.log(entry.id,JSON.stringify(result.runs.map(run=>({ms:run.captureWallMs,samples:run.samples,captureSamples:run.captureStackSamples,top:run.captureFrames.slice(0,5).map(row=>({name:row.name,self:row.selfPercent,inclusive:row.inclusivePercent}))}))));
}
console.log('Raw profiles, function maps, diagnostic WASM and summary: '+relative(root,out));
