import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import {Worker,isMainThread,parentPort,workerData} from 'node:worker_threads';
import {controlSchedule,controlRatios,statistics} from './lib/runtime-control-design.mjs';
import {AVR_CACHE_COMPILER_ID,AVR_CACHE_SOURCES} from '../lib/avr-cache-identity.js';
import {avr,IO,flash} from '../tests/fixtures/attiny13a-system-firmware.mjs';
import {parseHex} from '../lib/hex.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {resolveAVRProfile} from '../lib/avr-profiles.js';
const root=fileURLToPath(new URL('../../',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex');
const json=v=>JSON.stringify(v,(_k,x)=>typeof x==='bigint'?x+'n':typeof x==='number'&&!Number.isFinite(x)?String(x):ArrayBuffer.isView(x)?Array.from(x):x);
const snapshot=c=>({state:c.state(),data:c.data,flash:c.rom,eeprom:c.eeprom,native:Array.from(c._state),irq:c.irqFrames,
  control:c.controlRequest,watchdog:c.watchdogResetCycle,debug:c.debugEnabled});
function spmImage(){
  const write=(io,v)=>[...avr.ldi(16,v),...avr.out(io,16)],target=0x100,newWords=[avr.ldi(20,0x5a)[0],0xcfff];
  const words=[...avr.ldi(30,0),...avr.ldi(31,1),...write(IO.SPMCSR,3),0x95e8];
  for(const [n,w] of newWords.entries())words.push(...avr.ldi(30,2*n),...avr.ldi(16,w&255),0x2e00,
    ...avr.ldi(16,w>>8),0x2e10,...write(IO.SPMCSR,1),0x95e8);
  words.push(...avr.ldi(30,0),...write(IO.SPMCSR,5),0x95e8);words.push(avr.rjmp(words.length,target/2)[0]);
  return flash({instructions:[words]},{at:target/2,instructions:[avr.ldi(20,0x11),[0xcfff]]});
}

async function observe({baseline,caseName,incremental}){
  const [{ATtiny13A:Old},{ATtiny13A:New}]=await Promise.all([
    import(pathToFileURL(join(baseline,'web-player/lib/attiny13a.js')).href),import('../lib/attiny13a.js')]);
  const Core=incremental?New:Old,hz=1000000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  const catalog=JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url)));
  const entry=catalog.entries.find(e=>e.id===(caseName==='audio-lumiere'?'lumiere-stereo':'rhythmic'));
  const physical={resumable:true,oscillatorHz:hz,osccalHz,fuseLow:0x72,fastIdle:false,
    nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
  const options={cacheTranslation:false,fastIdle:false,incrementalCompilation:incremental,
    ...(caseName.startsWith('audio-')?nominalVerificationDeviceOptions(entry.cpuHz):
      caseName==='spm-compatible'?{}:physical),
    ...(caseName.startsWith('spm-')?{fuseHigh:0xef,spmCommandCycles:4}:{}),
    ...(caseName==='spm-clki'?{osccalHz:undefined,fuseLow:0x70,
      clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}}:{})};
  const image=caseName.startsWith('spm-')?spmImage():parseHex(entry.flashHex);
  const began=performance.now(),c=new Core(image,null,options),constructionMs=performance.now()-began;
  const trace=createHash('sha256'),checkpoints=[];let ms=0,pins=0,pcmSha256=null;
  const timed=fn=>{const start=performance.now(),value=fn();ms+=performance.now()-start;return value;};
  const drain=()=>{const p=c._ps?c.drainPinsPs():c.drainPins();pins+=p.length;trace.update(json(p));};
  if(caseName==='host-patches'){
    for(let n=0;n<16;n++){
      const word=avr.ldi(20,0x40+n)[0];c.rom[256]=word;c.rom[257]=word>>8;timed(()=>c._compile());
      checkpoints.push({translatedSha256:sha(c.transpiledBytes),diagnostics:c.incrementalCompilation??null});
    }
    drain();
  }else if(caseName.startsWith('audio-')){
    const pcm=timed(()=>c.capturePhysical(4096,48000,entry.audioChannels||1));
    pcmSha256=sha(new Uint8Array(pcm.buffer,pcm.byteOffset,pcm.byteLength));drain();assert.ok(c.state().irqs>0);
  }else{
    if(caseName==='spm-clki')c.injectClkiPeriodicPs({startPs:0n,initialLevel:1,highPs:500000n,lowPs:500000n,
      transitionCount:40000n,knownUntilPs:20000000000n});
    if(caseName==='spm-compatible')timed(()=>c.runUntil(200000n));
    else if(caseName==='spm-physical')timed(()=>c.runUntilPs(20000000000n));
    else for(let at=200000000n;at<=20000000000n;at+=200000000n){timed(()=>c.runUntilPs(at));drain();}
    if(caseName!=='spm-clki')drain();
    assert.equal(c.r[20],0x5a);assert.equal(c._exports.avr_device_generation(),2n);
  }
  assert.equal(c.state().deviceFault,0);
  return {ms,constructionMs,snapshotSha256:sha(json(snapshot(c))),translatedSha256:sha(c.transpiledBytes),
    pinSha256:trace.digest('hex'),pins,pcmSha256,diagnostics:c.incrementalCompilation??null,checkpoints};
}

if(!isMainThread){try{parentPort.postMessage(await observe(workerData));}catch(e){parentPort.postMessage({error:e.stack});}}
else{
  const {values}=parseArgs({options:{baseline:{type:'string',default:'9b1073f9'},trials:{type:'string',default:'8'},out:{type:'string',default:'build/benchmarks/incremental-compilation.json'}}});
  const trials=Number(values.trials),schedule=controlSchedule(trials);
  const commit=execFileSync('git',['rev-parse','--verify',values.baseline+'^{commit}'],{cwd:root,encoding:'utf8'}).trim();
  mkdirSync(join(root,'build/benchmarks'),{recursive:true});
  const baseline=mkdtempSync(join(root,'build/benchmarks/incremental-baseline-'));
  const sourceFiles=execFileSync('git',['ls-tree','-r','--name-only',commit,'web-player/lib'],{cwd:root,encoding:'utf8'}).trim().split('\n').filter(p=>p.endsWith('.js'));
  const baselineSources={};
  for(const p of [...sourceFiles,'web-player/package.json','web-player/wasm/attiny13a.wasm','web-player/wasm/avr.wasm']){
    const bytes=execFileSync('git',['show',commit+':'+p],{cwd:root,maxBuffer:16*1024*1024});
    mkdirSync(dirname(join(baseline,p)),{recursive:true});writeFileSync(join(baseline,p),bytes);
    baselineSources[p]=sha(p.endsWith('.wasm')?bytes:bytes.toString('utf8').replaceAll('\r\n','\n'));
  }
  const native=readFileSync(join(root,'web-player/wasm/attiny13a.wasm'));
  assert.equal(sha(native),baselineSources['web-player/wasm/attiny13a.wasm']);
  const report={schema:'micromusic-incremental-compilation-benchmark-v1',baselineCommit:commit,baselineSources,
    compilerIdentity:AVR_CACHE_COMPILER_ID,compilerGraph:AVR_CACHE_SOURCES,harnessSha256:sha(readFileSync(fileURLToPath(import.meta.url),'utf8').replaceAll('\r\n','\n')),
    nativeSha256:sha(native),node:process.version,v8:process.versions.v8,at:new Date().toISOString(),trials,
    hardwareTested:false,realtimeTested:false,
    timing:'Sequential fresh Workers. Construction separately; patching excludes host writes/hashes; SPM includes execution and retranslation; audio includes physical capture. CLKI trace drain excluded.',
    cases:[]};
  const [oldCompiler,newCompiler]=await Promise.all([
    import(pathToFileURL(join(baseline,'web-player/lib/avr-transpiler.js')).href),import('../lib/avr-transpiler.js')]);
  const legacyExports=new WebAssembly.Instance(await WebAssembly.compile(readFileSync(join(root,'web-player/wasm/avr.wasm')))).exports;
  const fullExports=new WebAssembly.Instance(await WebAssembly.compile(native)).exports;
  const legacyABI=newCompiler.runtimeABI(legacyExports),fullABI=newCompiler.runtimeABI(fullExports),phaseABI=newCompiler.runtimeABI(fullExports,{resumable:true});
  report.artifactParity=[];
  for(const entry of JSON.parse(readFileSync(new URL('../firmware.json',import.meta.url))).entries){
    const profile=resolveAVRProfile(entry.device),image=parseHex(entry.flashHex,profile.flashBytes);
    const modes=[['legacy',legacyABI,{}],...(profile.id==='attiny13a'?
      [['full',fullABI,{}],['resumable',phaseABI,{resumable:true}],['bounded-phase-locals',phaseABI,{resumable:true,boundedRegions:true,optimizePhaseLocals:true}]]:[])];
    for(const [mode,abi,policy] of modes){
      const options={device:profile.name,...policy};
      const old=oldCompiler.transpileAVR(image,abi,options),ordinary=newCompiler.transpileAVR(image,abi,options);
      assert.deepEqual(ordinary.bytes,old.bytes,entry.id+' / '+mode+' ordinary artifact');
      if(abi.device)assert.deepEqual(newCompiler.transpileAVR(image,abi,{...options,_linkage:true}).bytes,old.bytes,entry.id+' / '+mode+' incremental artifact');
      report.artifactParity.push({id:entry.id,mode,sha256:sha(old.bytes),bytes:old.bytes.length});
    }
  }
  console.log('Portable artifact comparisons: '+report.artifactParity.length+' identical to baseline.');
  function run(caseName,variant){return new Promise((resolve,reject)=>{
    const worker=new Worker(new URL(import.meta.url),{workerData:{baseline,caseName,incremental:variant.startsWith('new')}});
    const timeout=setTimeout(()=>{worker.terminate();reject(Error('Benchmark Worker timeout'));},60000);
    worker.on('error',e=>{clearTimeout(timeout);worker.terminate();reject(e);});
    worker.on('message',result=>{clearTimeout(timeout);worker.terminate();result.error?reject(Error(result.error)):resolve(result);});
  });}
  for(const caseName of ['host-patches','spm-compatible','spm-physical','spm-clki','audio-rhythmic','audio-lumiere']){
    const record={caseName,warmups:[],runs:[]};report.cases.push(record);
    for(const variant of ['oldA','oldB','newA','newB'])record.warmups.push({variant,...await run(caseName,variant)});
    const expected=record.warmups[0];
    for(let trial=0;trial<trials;trial++)for(const [position,variant] of schedule[trial].entries()){
      const result=await run(caseName,variant);
      for(const key of ['snapshotSha256','translatedSha256','pinSha256','pins','pcmSha256'])assert.equal(result[key],expected[key],caseName+' '+key);
      assert.deepEqual(result.checkpoints.map(c=>c.translatedSha256),expected.checkpoints.map(c=>c.translatedSha256));
      record.runs.push({trial,position,variant,...result});
    }
    record.execution=controlRatios(record.runs,trials);
    record.construction=controlRatios(record.runs.map(r=>({...r,ms:r.constructionMs})),trials);
    record.ordinaryMs=statistics(record.runs.filter(r=>r.variant.startsWith('old')).map(r=>r.ms));
    record.incrementalMs=statistics(record.runs.filter(r=>r.variant.startsWith('new')).map(r=>r.ms));
    console.log(JSON.stringify({caseName,oldMs:record.ordinaryMs.median,newMs:record.incrementalMs.median,
      execution:record.execution.crossVersion,construction:record.construction.crossVersion}));
  }
  report.passed=true;mkdirSync(dirname(join(root,values.out)),{recursive:true});writeFileSync(join(root,values.out),JSON.stringify(report,null,2)+'\n');
}
