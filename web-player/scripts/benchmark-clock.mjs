import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {cpus,platform,release,arch} from 'node:os';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseArgs} from 'node:util';
import {ATtiny13A,runtimeModule} from '../lib/attiny13a.js';
import {AVRCore as LegacyTranslated} from '../lib/avr-transpiled.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';

const root=fileURLToPath(new URL('../../',import.meta.url));
const {values}=parseArgs({options:{instructions:{type:'string',default:'1000000'},
  frames:{type:'string',default:'1200'},trials:{type:'string',default:'7'},
  out:{type:'string',default:'build/benchmarks/clock-current.json'},help:{type:'boolean'}}});
if(values.help){
  console.log('node web-player/scripts/benchmark-clock.mjs [--instructions 1000000] [--frames 1200] [--trials 7] [--out build/benchmarks/clock-current.json]');
  process.exit(0);
}
function integer(value,min,max,name){
  const n=Number(value);assert.ok(Number.isInteger(n)&&n>=min&&n<=max,`${name} must be${min}..${max}`);return n;
}
const instructions=integer(values.instructions,1000,10000000,'instructions');
const frames=integer(values.frames,48,48000,'frames'),trials=integer(values.trials,3,31,'trials'),rate=48000;
const endPs=BigInt(frames)*1000000000000n/BigInt(rate),seconds=Number(endPs)/1e12;
const hash=value=>createHash('sha256').update(value).digest('hex');
const source=path=>readFileSync(resolve(root,path),'utf8').replaceAll('\r\n','\n');
const runtimePath='web-player/wasm/attiny13a.wasm',manifestPath='web-player/wasm/device-build.json';
const runtime=readFileSync(resolve(root,runtimePath)),manifest=JSON.parse(source(manifestPath));
assert.equal(hash(runtime),manifest.artifacts['attiny13a.wasm']);
for(const [path,expected] of Object.entries(manifest.inputs))assert.equal(hash(source(path)),expected,path+' build mismatch');
assert.deepEqual(WebAssembly.Module.imports(runtimeModule),[]);
const git=args=>{try{return execFileSync('git',args,{cwd:root,encoding:'utf8'}).trim();}catch{return null;}};
const paths=['web-player/scripts/benchmark-clock.mjs','web-player/lib/attiny13a-runtime.js',
  'web-player/lib/avr-transpiled-runtime.js','web-player/lib/avr-transpiler.js',
  'web-player/lib/avr-wasm-phases.js','web-player/lib/avr-runtime.js',
  'web-player/tests/fixtures/attiny13a-system-firmware.mjs'];
const program=flash({instructions:[avr.ldi(16,1),avr.ldi(17,0x55),avr.add(18,16),
  avr.eor(19,17),avr.inc(20),avr.rjmp(5,2)]});
function table(hz){const result=Array(128).fill(0);result[0]=hz;return result;}
function createPhysical(hz,external=false){
  return new ATtiny13A(program,null,{resumable:true,fastIdle:false,oscillatorHz:hz,
    fuseLow:external?0x70:0x72,...external?{clkiProfile:{
      phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{osccalHz:table(hz)}});
}
function cpu(c){return{cycles:c.cyc,pc:c.pc,sp:c.sp,sreg:c.sreg,registers:Array.from(c.r)};}
function validate(c,retired){
  assert.equal(c.r[16],1);assert.equal(c.r[17],0x55);
  const n=retired-2;
  assert.equal(c.r[18],Math.floor((n+3)/4)&255,'ADD executions');
  assert.equal(c.r[19],(Math.floor((n+2)/4)&1)?0x55:0,'EOR executions');
  assert.equal(c.r[20],Math.floor((n+1)/4)&255,'INC executions');
  assert.equal(c.pc,2+n%4,'retired instruction PC');
  if(c.state().cpuPhase)assert.equal(c.state().cpuPhase.retired,BigInt(retired));
}
function fromHalf(half){
  const cycles=Math.floor(half/2),remaining=cycles-2;
  return 2+Math.floor(remaining/5)*4+Math.min(remaining%5,3);
}
function stats(samples){
  const sorted=[...samples].sort((a,b)=>a-b),mean=samples.reduce((a,b)=>a+b,0)/samples.length;
  return{median:sorted.length%2?sorted[sorted.length>>1]:(sorted[sorted.length/2-1]+sorted[sorted.length/2])/2,
    min:sorted[0],max:sorted.at(-1),mean,
    standardDeviation:Math.sqrt(samples.reduce((sum,n)=>sum+(n-mean)**2,0)/(samples.length-1))};
}
const report={schema:'micromusic-clock-benchmark-v1',createdAt:new Date().toISOString(),
  git:{head:git(['rev-parse','HEAD']),branch:git(['branch','--show-current']),status:git(['status','--short'])},
  host:{node:process.version,v8:process.versions.v8,flags:process.execArgv,platform:platform(),
    release:release(),arch:arch(),cpu:cpus()[0]?.model,logicalCpus:cpus().length},
  provenance:{runtimeSha256:hash(runtime),runtimeBytes:runtime.length,manifestSha256:hash(source(manifestPath)),
    runtimeSourceHashes:manifest.inputs,sourceSha256NormalizedLF:Object.fromEntries(paths.map(path=>[path,hash(source(path))])),
    flashSha256:hash(program)},
  parameters:{instructions,frames,rate,seconds,endPs:endPs.toString(),trials},
  method:{kernel:'LDI r16,1; LDI r17,0x55; loop: ADD r18,r16; EOR r19,r17; INC r20; RJMP loop. The loop retires4instructions per5CPUcycles. No timer/PWM is enabled.',
    timing:'Serial warmed Node runs. Fresh memory per run, construction and input submission outside timers, no profiling/forcedGC/CPUaffinity. Rotate/reverse case order between trials. V8/GC/other host load remain in samples.',
    direct:'One public run(N) call. Native full-device cases include the real peripheral scheduler and IRQ checks even with unused devices. Legacy translated is the limited historical runtime, not equal hardware coverage. These are throughput tests, not exclusive CPU-function instrumentation.',
    clock:'Only public capturePhysical calls are timed. 25ms by default, 48kHz mono constant-low output. Full native CPU, scheduler, source/PB3 pin capture, native integration and wrapper copying remain coupled. Descriptors are submitted before timing, every supplied CLKI transition is still serviced.',
    divider:'Both physical modes start D1 then receive the same protected CLKPR request at time0. One old source cycle precedes the selected new divisor, avoiding a difference in initial divider phase.',
    validation:'Independent program/count/register/cycle assertions, no faults, exact PCM=-1, deterministic per-case CPU snapshots and byte-for-byte CPU equivalence between internal physical source and matching CLKI waveform at each frequency/divisor. Compilation/construction/hashing/assertions are outside execution timers.',
    limits:'Node host results, not browser/AudioWorklet latency or silicon measurements. Constant-output kernel is not representative of music; use benchmark-device.mjs for firmware/PWM/DSP.'},
  direct:[],clock:[]};
const direct=[
  {id:'legacy-translated',make:()=>new LegacyTranslated(program,null,{fastIdle:false})},
  {id:'full-compatible',make:()=>new ATtiny13A(program,null,{fastIdle:false})},
  {id:'full-physical-resumable',make:()=>createPhysical(9600000)},
];
const reference=new Map();
function directRun(entry){
  const c=entry.make(),start=performance.now();const count=c.run(instructions),ms=performance.now()-start;
  assert.equal(count,instructions);assert.equal(c.cyc,instructions+Math.floor((instructions-2)/4));
  validate(c,count);assert.equal(c.state().deviceFault??0,0);
  const snapshot=cpu(c),baseline=reference.get('direct');
  if(baseline)assert.deepEqual(snapshot,baseline);else reference.set('direct',snapshot);
  return{ms,retired:count,cycles:c.cyc,snapshotSha256:hash(JSON.stringify(snapshot)),
    translatedBytes:c.transpiledBytes.length,cacheHit:c.translationCacheHit};
}
console.log(`Direct kernel: ${instructions}instructions per run`);
for(const entry of direct){directRun(entry);entry.runs=[];}
for(let trial=0;trial<trials;trial++)for(const entry of [...direct.slice(trial%direct.length),...direct.slice(0,trial%direct.length)])
  entry.runs.push({trial,...directRun(entry)});
for(const entry of direct){
  const summary=stats(entry.runs.map(r=>r.ms));
  report.direct.push({id:entry.id,runs:entry.runs,executionMs:summary,
    millionInstructionsPerSecond:instructions/(summary.median*1000),
    millionCyclesPerSecond:entry.runs[0].cycles/(summary.median*1000)});
}
const clocks=[];
for(const hz of [1000000,10000000,20000000])for(const divisor of [1,8,256])for(const external of [false,true])
  clocks.push({id:`${external?'clki':'internal'}-${hz}-div${divisor}`,hz,divisor,external,runs:[]});
function clockRun(entry){
  const c=createPhysical(entry.hz,entry.external),exponent=Math.log2(entry.divisor);
  c.writeIO(IO.CLKPR,128);c.writeIO(IO.CLKPR,exponent);
  if(entry.external){
    const width=1000000000000n/BigInt(2*entry.hz),count=endPs/width;
    assert.equal(c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:width,lowPs:width,
      transitionCount:count,knownUntilPs:endPs}),true);
  }
  const start=performance.now(),pcm=c.capturePhysical(frames,rate),ms=performance.now()-start;
  const period=1000000000000n/BigInt(entry.hz);
  const expectedHalf=2n+(endPs-period)*BigInt(2*entry.hz)/(1000000000000n*BigInt(entry.divisor));
  assert.equal(c.cyc,Number(expectedHalf)/2,'elapsed source/divider CPU phases');
  const retired=fromHalf(Number(expectedHalf));validate(c,retired);
  assert.equal(c.state().timePs,endPs);assert.equal(c.state().deviceFault,0);
  assert.equal(c.state().clockDivisor,entry.divisor);assert.ok(pcm.every(v=>v===-1));
  const snapshot={...cpu(c),phase:c.state().cpuPhase},key=`${entry.hz}/${entry.divisor}`;
  if(reference.has(key))assert.deepEqual(snapshot,reference.get(key),entry.id+' CPU/phase parity');
  else reference.set(key,snapshot);
  return{ms,retired,cycles:c.cyc,snapshotSha256:hash(JSON.stringify(snapshot,(_,v)=>typeof v==='bigint'?v.toString():v)),
    pcmSha256:hash(new Uint8Array(pcm.buffer)),sourceTransitions:entry.external?Number(endPs/ (period/2n)):null,
    translatedBytes:c.transpiledBytes.length};
}
console.log(`Physical clocks: ${clocks.length}cases, ${seconds*1000}ms each, ${trials}trials`);
for(const entry of clocks)clockRun(entry);
for(let trial=0;trial<trials;trial++){
  const ordered=[...clocks.slice(trial%clocks.length),...clocks.slice(0,trial%clocks.length)];
  if(trial%2)ordered.reverse();
  for(const entry of ordered)entry.runs.push({trial,...clockRun(entry)});
  console.log(`Clock trial${trial+1}/${trials} complete`);
}
for(const {runs,...entry} of clocks){
  const summary=stats(runs.map(r=>r.ms));
  report.clock.push({...entry,runs,captureMs:summary,realtime:seconds*1000/summary.median,
    millionInstructionsPerSecond:runs[0].retired/(summary.median*1000),
    millionCyclesPerSecond:runs[0].cycles/(summary.median*1000)});
}
report.complete=true;report.completedAt=new Date().toISOString();
const output=resolve(root,values.out);mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,JSON.stringify(report,null,2)+'\n');
console.table(report.direct.map(r=>({engine:r.id,ms:r.executionMs.median.toFixed(2),
  MIPS:r.millionInstructionsPerSecond.toFixed(3),MHz:r.millionCyclesPerSecond.toFixed(3)})));
console.table(report.clock.map(r=>({engine:r.id,ms:r.captureMs.median.toFixed(2),
  realtime:r.realtime.toFixed(3)+'x',MIPS:r.millionInstructionsPerSecond.toFixed(3)})));
console.log('All instruction/phase/PCM checks passed. Report: '+output);
