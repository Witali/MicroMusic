// Compare two generators against the same native runtime and host adapter.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {resolve,join,dirname} from 'node:path';
import {cpus,platform,release} from 'node:os';
import {parseArgs} from 'node:util';
import {ATtiny13A} from '../lib/attiny13a-runtime.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';
import {controlLabels,controlSchedule,controlRatios} from './lib/runtime-control-design.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{'baseline-ref':{type:'string',default:'fc40b21a'},
  'validate-only':{type:'boolean'},frames:{type:'string',default:'12000'},
  'kernel-frames':{type:'string',default:'1200'},trials:{type:'string',default:'8'},
  warmups:{type:'string',default:'4'},case:{type:'string',multiple:true},
  out:{type:'string',default:'build/benchmarks/region-budgets.json'}}});
const integer=(v,min,max)=>{const n=Number(v);assert.ok(Number.isInteger(n)&&n>=min&&n<=max);return n;};
const frames=integer(values.frames,1024,48000),kernelFrames=integer(values['kernel-frames'],1200,48000),
  trials=integer(values.trials,8,32),warmups=integer(values.warmups,4,8),rate=48000,block=1024,schedule=controlSchedule(trials);
const sha=b=>createHash('sha256').update(b).digest('hex');
const stringify=v=>JSON.stringify(v,(_,x)=>typeof x==='bigint'?x.toString():x,2)+'\n';
const text=p=>readFileSync(resolve(root,p),'utf8').replaceAll('\r\n','\n');
const git=args=>execFileSync('git',args,{cwd:root,maxBuffer:16*1024*1024});
const baseline=git(['rev-parse',values['baseline-ref']+'^{commit}']).toString().trim();
const targets=['web-player/lib/avr-transpiler.js','web-player/lib/avr-wasm-regions.js'];
// Check every tracked library input, not merely the two named generator files.
const paths=git(['ls-tree','-r','--full-tree','--name-only',baseline,'web-player/lib']).toString().trim().split('\n');
const historical=new Map(paths.map(p=>[p,git(['show',baseline+':'+p]).toString().replaceAll('\r\n','\n')]));
assert.deepEqual(paths.filter(p=>text(p)!==historical.get(p)),targets);
const baseDir=resolve(root,'build/benchmarks/region-generators');mkdirSync(baseDir,{recursive:true});
const isolated=mkdtempSync(join(baseDir,'baseline-'));
writeFileSync(join(isolated,'regions.mjs'),historical.get(targets[1]));
const factory=historical.get(targets[0]).replace(/from '([^']+)'/g,(_,p)=>
  "from '"+pathToFileURL(p==='./avr-wasm-regions.js'?join(isolated,'regions.mjs'):resolve(root,'web-player/lib',p)).href+"'");
writeFileSync(join(isolated,'transpiler.mjs'),factory);
const oldTranspile=(await import(pathToFileURL(join(isolated,'transpiler.mjs')).href)).transpileAVR;
const nativeBytes=readFileSync(resolve(root,'web-player/wasm/attiny13a.wasm'));
const manifest=JSON.parse(text('web-player/wasm/device-build.json'));
assert.equal(sha(nativeBytes),manifest.artifacts['attiny13a.wasm']);
assert.ok(nativeBytes.equals(git(['show',baseline+':web-player/wasm/attiny13a.wasm'])));
for(const [p,h]of Object.entries(manifest.inputs))assert.equal(sha(text(p)),h,p);
const nativeModule=new WebAssembly.Module(nativeBytes);
assert.deepEqual(WebAssembly.Module.imports(nativeModule),[]);
const abi=runtimeABI(new WebAssembly.Instance(nativeModule).exports,{resumable:true});
const table=hz=>{const t=Array(128).fill(0);t[0]=hz;return t;};
const catalogs=['web-player/firmware.json','web-player/hq4-firmware.json'].map(p=>JSON.parse(text(p)));
const catalog=catalogs.flatMap(x=>x.entries),aliases=Object.assign({},...catalogs.map(x=>x.aliases));
const cases=['rhythmic','lumiere-stereo','hq4-chego-auto'].map(id=>{
  const entry=catalog.find(x=>x.id===(aliases[id]??id));assert.ok(entry);
  const binary=parseHex(entry.flashHex),hz=entry.cpuHz||9600000;assert.equal(sha(binary),entry.flashSha256);
  return {id:id+'-physical',binary,eeprom:entry.eepromHex?parseHex(entry.eepromHex,64):null,
    frames,channels:entry.audioChannels||1,options:{oscillatorHz:hz,osccalHz:table(hz),resumable:true,
      boundedRegions:true,nvmClockProfile:1,nvmCalibrationReferenceHz:hz}};
});
const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
for(const external of [false,true])cases.push({id:'kernel-'+(external?'clki':'internal')+'-20m',binary:kernel,
  frames:kernelFrames,channels:1,external,options:{oscillatorHz:20000000,resumable:true,boundedRegions:true,
    fuseLow:external?0x70:0x72,...external?{clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz:table(20000000)}}});
const selected=values.case?cases.filter(x=>values.case.includes(x.id)):cases;
assert.ok(selected.length);if(values.case)assert.equal(selected.length,values.case.length);
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irq:Array.from(c.irqFrames)});
function construct(item,generated){
  const c=new ATtiny13A(item.binary,item.eeprom,{...item.options,runtimeModule:nativeModule,precompiled:generated});
  assert.ok(Buffer.from(c.transpiledBytes).equals(Buffer.from(generated.bytes)));
  assert.equal(c.pinObservation.mask,63);assert.equal(c.pinObservation.retainDuringAudio,false);
  if(item.id.startsWith('kernel-')){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,0);}
  if(item.external){const end=BigInt(item.frames)*1000000000000n/BigInt(rate);
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:25000n,transitionCount:end/25000n,knownUntilPs:end}),true);
  }else{c.injectPinsPs({at:777777n,mask:4,levels:4});c.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});}
  return c;
}
function execute(c,item){
  let ms=0;const pcm=[],snapshots=[];
  for(let offset=0;offset<item.frames;offset+=block){
    const start=performance.now(),raw=c.capturePhysical(Math.min(block,item.frames-offset),rate,item.channels);ms+=performance.now()-start;
    pcm.push(Buffer.from(raw.buffer,raw.byteOffset,raw.byteLength));snapshots.push(snapshot(c));
  }
  snapshots.forEach(x=>assert.equal(x.state.deviceFault,0));
  const raw=Buffer.concat(pcm),pins=c.drainPinsPs();
  return {raw,snapshots,pins,record:{ms,rawSha256:sha(raw),architectureSha256:sha(stringify(snapshots)),
    pinSha256:sha(stringify(pins)),checkpoints:snapshots.length,finalState:c.state()}};
}
const same=(a,b)=>{assert.ok(a.raw.equals(b.raw));assert.deepEqual(a.snapshots,b.snapshots);assert.deepEqual(a.pins,b.pins);};
const sourcePaths=[...paths,'web-player/scripts/benchmark-region-budgets.mjs','web-player/scripts/lib/runtime-control-design.mjs',
  'web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
const out=resolve(root,values.out);mkdirSync(dirname(out),{recursive:true});
const report={schema:'micromusic-region-budget-controls-v1',complete:false,createdAt:new Date().toISOString(),
  baseline,gitHead:git(['rev-parse','HEAD']).toString().trim(),mode:values['validate-only']?'validation':'timing',
  host:{node:process.version,v8:process.versions.v8,flags:process.execArgv,platform:platform(),release:release(),cpu:cpus()[0]?.model},
  parameters:{frames,kernelFrames,trials,warmups,rate,block,schedule},
  provenance:{nativeSha256:sha(nativeBytes),nativeBytes:nativeBytes.length,changedInputs:targets,
    sourceSha256:Object.fromEntries(sourcePaths.map(p=>[p,sha(text(p))])),
    baselineGeneratorSha256:Object.fromEntries(targets.map(p=>[p,sha(historical.get(p))]))},
  method:'Only the two generator sources differ. Historical relative imports are redirected to byte-unchanged current dependencies in an ignored factory. All labels use one unchanged native Module, host/options and fresh instances. CPU bytes are identical within oldA/oldB and newA/newB; construction/compilation, input setup, snapshots and hashing are outside capture timers. Equal full-workload warmups and serial Williams trials retain identity controls. Every checkpoint compares full public/diagnostic state, memories/IRQ, exact PCM and retained pin history. Profiled/exclusive times and browser speed are not inferred. Host load/frequency/JIT/GC remain uncontrolled.',results:[]};
for(const item of selected){
  const old=oldTranspile(item.binary,abi,item.options),current=transpileAVR(item.binary,abi,item.options);
  assert.ok(Buffer.from(oldTranspile(item.binary,abi,{...item.options,boundedRegions:false}).bytes)
    .equals(Buffer.from(transpileAVR(item.binary,abi,{...item.options,boundedRegions:false}).bytes)),'ordinary CPU bytes unchanged');
  assert.deepEqual(old.manifest,current.manifest,'same target, ABI, flags and region plans');
  const row={id:item.id,options:item.options,frames:item.frames,channels:item.channels,flashSha256:sha(item.binary),
    generated:Object.fromEntries([['old',old],['new',current]].map(([k,g])=>[k,{bytes:g.bytes.length,sha256:sha(g.bytes)}])),warmups:[],runs:[]};
  console.log(item.id);let reference;
  const run=(label,record)=>{const result=execute(construct(item,label.startsWith('old')?old:current),item);
    if(reference)same(result,reference);else reference=result;record.push({variant:label,...result.record});};
  if(values['validate-only']){run('oldA',row.runs);run('newA',row.runs);}
  else{
    for(let pass=0;pass<warmups;pass++)for(const [position,label]of schedule[pass].entries()){
      run(label,row.warmups);Object.assign(row.warmups.at(-1),{pass,position});}
    for(let trial=0;trial<trials;trial++)for(const [position,label]of schedule[trial].entries()){
      run(label,row.runs);Object.assign(row.runs.at(-1),{trial,position});}
    row.ratios=controlRatios(row.runs,trials);
  }
  row.checkpointsCompared=(row.warmups.length+row.runs.length-1)*reference.snapshots.length;
  report.results.push(row);report.complete=report.results.length===selected.length;writeFileSync(out,stringify(report));
}
console.log('Exact region-budget controls passed: '+out);
