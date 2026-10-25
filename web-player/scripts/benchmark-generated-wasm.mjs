// Generated CPU optimizer experiment; the production peripheral runtime is read-only.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {cpus,platform} from 'node:os';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {runtimeABI,transpileAVR} from '../lib/avr-transpiler.js';
import {parseHex} from '../lib/hex.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';
import {optimizeAVRWasm} from './lib/optimize-avr-wasm.mjs';
import {controlLabels,controlSchedule,controlRatios} from './lib/runtime-control-design.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{level:{type:'string',multiple:true},case:{type:'string',multiple:true},
  'validate-only':{type:'boolean'},
  transform:{type:'string',default:'binaryen'},'baseline-ref':{type:'string'},
  trials:{type:'string',default:'8'},warmups:{type:'string',default:'4'},frames:{type:'string',default:'12000'},
  instructions:{type:'string',default:'1000000'},out:{type:'string',default:'build/benchmarks/generated-wasm.json'},'wasm-opt':{type:'string'}}});
const integer=(s,min,max)=>{const n=Number(s);assert.ok(Number.isInteger(n)&&n>=min&&n<=max);return n;};
const trials=integer(values.trials,8,32),schedule=controlSchedule(trials),warmups=integer(values.warmups,1,8),
  frames=integer(values.frames,1024,48000),instructions=integer(values.instructions,1000,10000000),rate=48000,block=1024;
const phaseLocals=values.transform==='phase-locals',bounded=values.transform==='bounded-regions',compilerTransform=phaseLocals||bounded;
assert.ok(compilerTransform||values.transform==='binaryen');
const allowed=phaseLocals?['live-locals']:bounded?['bounded-regions']:['O2','O3','Os','Oz'];
const levels=values.level??(compilerTransform?allowed:['O3','Oz']);assert.equal(new Set(levels).size,levels.length);
assert.ok(levels.length&&levels.every(level=>allowed.includes(level)));
const sha=b=>createHash('sha256').update(b).digest('hex');
const stringify=v=>JSON.stringify(v,(_,n)=>typeof n==='bigint'?n.toString():n,2)+'\n';
const source=p=>readFileSync(resolve(root,p),'utf8').replaceAll('\r\n','\n');
let previousGenerator,baseline;
if(values['baseline-ref']){
  const revision=execFileSync('git',['rev-parse',values['baseline-ref']+'^{commit}'],{cwd:root,encoding:'utf8'}).trim();
  const paths=['web-player/lib/avr-transpiler.js','web-player/lib/avr-wasm-phases.js'];
  const originals=paths.map(p=>execFileSync('git',['show',revision+':'+p],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n'));
  const url=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64');
  let phaseSource=originals[1];
  const dependencyNames=['avr-phase-locals.js','avr-wasm-regions.js'];
  for(const name of dependencyNames)if(originals.some(s=>s.includes("'./"+name+"'"))){
    const dependency='web-player/lib/'+name;
    const historical=execFileSync('git',['show',revision+':'+dependency],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n');
    assert.equal(historical,source(dependency),'Historical compiler dependency must be unchanged');
    phaseSource=phaseSource.replace("'./"+name+"'",JSON.stringify(new URL('../lib/'+name,import.meta.url).href));
    paths.push(dependency);originals.push(historical);
  }
  let compiler=originals[0].replace("'./devices/profiles.js'",JSON.stringify(new URL('../lib/devices/profiles.js',import.meta.url).href))
    .replace("'./avr-wasm-phases.js'",JSON.stringify(url(phaseSource)));
  for(const name of dependencyNames)compiler=compiler.replace("'./"+name+"'",JSON.stringify(new URL('../lib/'+name,import.meta.url).href));
  previousGenerator=(await import(url(compiler))).transpileAVR;
  baseline={revision,sourceSha256:Object.fromEntries(paths.map((p,n)=>[p,sha(originals[n])])),
    adaptation:'Only import URLs are redirected: historical phase module as data URL, unchanged device profiles/phase-local dependency as file URLs.'};
}
const catalogs=['web-player/firmware.json','web-player/hq4-firmware.json'].map(p=>JSON.parse(source(p)));
const catalog=catalogs.flatMap(c=>c.entries),aliases=Object.assign({},...catalogs.map(c=>c.aliases));
const hzTable=hz=>{const table=Array(128).fill(0);table[0]=hz;return table;};
const cases=[];
for(const id of ['rhythmic','lumiere-stereo','hq4-chego-auto']){
  const entry=catalog.find(e=>e.id===(aliases[id]??id));assert.ok(entry);const binary=parseHex(entry.flashHex);assert.equal(sha(binary),entry.flashSha256);
  for(const physical of [false,true])cases.push({id:id+'-'+(physical?'physical':'compatible'),actualId:entry.id,binary,
    eeprom:entry.eepromHex?parseHex(entry.eepromHex,64):undefined,frames,channels:entry.audioChannels||1,physical,
    options:{oscillatorHz:entry.cpuHz||9600000,...physical?{resumable:true,osccalHz:hzTable(entry.cpuHz||9600000),nvmClockProfile:1,nvmCalibrationReferenceHz:entry.cpuHz||9600000}:{}}});
}
const kernel=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
for(const physical of [false,true])cases.push({id:'kernel-'+(physical?'physical':'compatible')+'-direct',binary:kernel,instructions,physical,
  options:{oscillatorHz:9600000,fuseLow:0x72,...physical?{resumable:true,osccalHz:hzTable(9600000)}:{}}});
for(const divisor of [1,256])cases.push({id:'kernel-clki-20m-div'+divisor,binary:kernel,frames:1200,channels:1,physical:true,external:true,divisor,
  options:{oscillatorHz:20000000,resumable:true,fuseLow:0x70,clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}});
cases.push({id:'kernel-internal-20m-div1',binary:kernel,frames:1200,channels:1,physical:true,divisor:1,
  options:{oscillatorHz:20000000,resumable:true,fuseLow:0x72,osccalHz:hzTable(20000000)}});
for(const id of ['kernel-internal-20m-div1','kernel-clki-20m-div1'])cases.push({...cases.find(c=>c.id===id),id:id+'-adc-active',adcEnabled:true});
const selected=values.case?cases.filter(c=>values.case.includes(c.id)):cases;assert.ok(selected.length);
if(values.case)assert.equal(selected.length,values.case.length,'Unknown or duplicate case');
function layout(bytes){
  let at=8;const leb=()=>{let n=0,shift=0,b;do{b=bytes[at++];n|=(b&127)<<shift;shift+=7;}while(b&128);return n;};
  const result={};while(at<bytes.length){const id=bytes[at++],length=leb(),end=at+length;
    if(id===10){result.codeSectionBytes=length;result.functions=leb();}if(id===0)result.customSectionBytes=(result.customSectionBytes||0)+length;at=end;}
  return result;
}
function construct(item,generated){
  // The phase-local experiment uses the normal production translation cache:
  // identical labels must share a CPU Module, as well as the native Module.
  const c=new ATtiny13A(item.binary,item.eeprom,{...item.options,optimizePhaseLocals:generated.manifest.optimizePhaseLocals??false,
    boundedRegions:generated.manifest.boundedRegions??false,runtimeModule,...compilerTransform?{}:{precompiled:generated}});
  assert.equal(sha(c.transpiledBytes),sha(generated.bytes));
  if(compilerTransform){
    item.cpuModules??=new Map();const key=sha(generated.bytes);
    if(item.cpuModules.has(key))assert.equal(c._translatedModule,item.cpuModules.get(key),'Identity labels must reuse the CPU Module');
    else item.cpuModules.set(key,c._translatedModule);
  }
  if(item.divisor){c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,Math.log2(item.divisor));}
  if(item.adcEnabled){c.writeIO(IO.ADMUX,3);c.writeIO(IO.ADCSRA,0xe7);}
  if(item.external){const end=BigInt(item.frames)*1000000000000n/BigInt(rate);
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:25000n,lowPs:25000n,transitionCount:end/25000n,knownUntilPs:end}),true);
  }else if(!item.instructions){
    if(item.physical){c.injectPinsPs({at:777777n,mask:4,levels:4});c.setAnalogPs({at:1601601n,pin:2,microvolts:1234567});}
    else{c.injectPins({at:777n,mask:4,levels:4});c.setAnalog({at:1601n,pin:2,microvolts:1234567});}
  }
  return c;
}
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:c.data.slice(),flash:c.rom.slice(),eeprom:c.eeprom.slice(),irq:Array.from(c.irqFrames)});
function execute(c,item){
  let ms=0;const pcm=[],states=[];
  if(item.instructions){const start=performance.now(),retired=c.run(item.instructions);ms=performance.now()-start;
    assert.equal(retired,item.instructions);assert.equal(c.cyc,item.instructions+Math.floor((item.instructions-2)/4));
    assert.equal(c.r[18],Math.floor((item.instructions+1)/4)&255);assert.equal(c.r[20],Math.floor((item.instructions-1)/4)&255);states.push(snapshot(c));
  }else for(let at=0;at<item.frames;at+=block){
    const n=Math.min(block,item.frames-at),start=performance.now(),raw=c.capturePhysical(n,rate,item.channels);ms+=performance.now()-start;
    pcm.push(Buffer.from(raw.buffer,raw.byteOffset,raw.byteLength));states.push(snapshot(c));
  }
  assert.equal(c.state().deviceFault,0);
  if(item.divisor)assert.equal(c.state().clockDivisor,item.divisor);
  if(item.adcEnabled)assert.equal(c.data[32+IO.ADCSRA]&0x90,0x90);
  const pins=item.physical?c.drainPinsPs():c.drainPins(),raw=Buffer.concat(pcm);
  return {raw,states,pins,ms,record:{rawSha256:sha(raw),stateSha256:sha(stringify(states)),pinSha256:sha(stringify(pins)),checkpoints:states.length}};
}
const output=resolve(root,values.out);mkdirSync(dirname(output),{recursive:true});
const support=['web-player/lib/avr-transpiler.js','web-player/lib/avr-wasm-phases.js','web-player/lib/avr-phase-locals.js','web-player/lib/avr-wasm-regions.js','web-player/lib/avr-transpiled-runtime.js','web-player/lib/attiny13a-runtime.js',
  'web-player/scripts/benchmark-generated-wasm.mjs','web-player/scripts/lib/optimize-avr-wasm.mjs','web-player/scripts/lib/runtime-control-design.mjs'];
const report={schema:'micromusic-generated-wasm-benchmark-v1',complete:false,revision:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
  mode:values['validate-only']?'validation':'timing',
  transform:values.transform,...baseline?{baseline}: {},
  cpuModulePolicy:compilerTransform?'production-translation-cache':'fresh-precompiled',
  gcBeforeRun:typeof globalThis.gc==='function',
  node:process.version,platform:platform(),cpu:cpus()[0].model,trials,warmups,rate,frames,instructions,levels,
  sourceSha256:Object.fromEntries(support.map(p=>[p,sha(source(p))])),runtimeSha256:sha(readFileSync(new URL('../wasm/attiny13a.wasm',import.meta.url))),
  method:'Timing mode: balanced four-label trials; oldA/oldB identical raw CPU bytes, newA/newB identical optimized bytes; one unchanged native Module. Phase-local runs use the production translation cache and assert CPU Module sharing within identity pairs; Binaryen runs use fresh precompiled CPU Modules. Instances/memories are always fresh. Equal warmups; construction, optimization and snapshots excluded from execution timing. Validation mode: one raw and one optimized run; no speed inference. Exact PCM, full architectural/diagnostic state and pins checked after every audio block or direct run. Ratios above1 favor optimized CPU. Generation/optimizer-process and compile observations are single observations, not cold-start medians or browser guarantees.',cases:[]};
const save=()=>writeFileSync(output,stringify(report));save();
for(const item of selected){
  const start=performance.now(),raw=transpileAVR(item.binary,runtimeABI(new WebAssembly.Instance(runtimeModule).exports,{resumable:!!item.options.resumable}),item.options),generationMs=performance.now()-start;
  if(previousGenerator)assert.deepEqual(raw.bytes,previousGenerator(item.binary,raw.manifest.abi,item.options).bytes,item.id+' must preserve baseline bytes');
  for(const level of levels){
    let optimized;
    if(compilerTransform){
      const setting=phaseLocals?{optimizePhaseLocals:true}:{boundedRegions:true};
      const start=performance.now(),generated=item.options.resumable?transpileAVR(item.binary,raw.manifest.abi,{...item.options,...setting}):raw;
      optimized={...generated,optimization:{tool:'generation-time '+values.transform,flags:item.options.resumable?[Object.keys(setting)[0]+'=true']:[],
        inputSha256:sha(raw.bytes),outputSha256:sha(generated.bytes),inputBytes:raw.bytes.length,outputBytes:generated.bytes.length,elapsedMs:performance.now()-start,
        phaseLocals:generated.manifest.stats.phaseLocals??null,...bounded?{regions:generated.manifest.stats.boundedRegions??null}:{}}};
    }else optimized=optimizeAVRWasm(raw,{level,wasmOpt:values['wasm-opt']});
    const compiled={};
    for(const [name,generated]of [['raw',raw],['optimized',optimized]]){const t=performance.now();new WebAssembly.Module(generated.bytes);compiled[name]=performance.now()-t;}
    const row={id:item.id,actualId:item.actualId,level,flashSha256:sha(item.binary),eepromSha256:item.eeprom?sha(item.eeprom):null,
      generationMs,compileAfterValidationMs:compiled,optimization:optimized.optimization,rawLayout:layout(raw.bytes),optimizedLayout:layout(optimized.bytes),runs:[],warmups:[]};
    const generated=variant=>variant.startsWith('old')?raw:optimized;let reference;
    const run=(variant,trial,position)=>{
      const core=construct(item,generated(variant));globalThis.gc?.();
      const result=execute(core,item);
      if(reference){assert.ok(result.raw.equals(reference.raw));assert.deepEqual(result.states,reference.states);assert.deepEqual(result.pins,reference.pins);}else reference=result;
      return{variant,trial,position,ms:result.ms,...result.record};
    };
    if(values['validate-only'])row.runs.push(run('oldA',0,0),run('newA',0,1));
    else{
      for(let n=0;n<warmups;n++)for(const [position,variant]of controlLabels.entries())row.warmups.push(run(variant,n,position));
      for(let trial=0;trial<trials;trial++)for(const [position,variant]of schedule[trial].entries())row.runs.push(run(variant,trial,position));
      row.ratios=controlRatios(row.runs,trials);
    }
    report.cases.push(row);save();
    console.log(JSON.stringify({case:row.id,level,bytes:row.optimization.outputBytes,rawBytes:row.optimization.inputBytes,
      oldIdentity:row.ratios?.oldIdentity.median,newIdentity:row.ratios?.newIdentity.median,cross:row.ratios?.crossVersion.median}));
  }
}
report.complete=true;save();
