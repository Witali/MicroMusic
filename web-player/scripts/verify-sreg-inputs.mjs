// Serial source-isolated correctness/size checks and paired execution controls.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {dirname,join,relative,isAbsolute} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import {parseHex} from '../lib/hex.js';
import {resolveAVRProfile} from '../lib/avr-profiles.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
const root=fileURLToPath(new URL('../../',import.meta.url)),read=p=>readFileSync(join(root,p));
const sha=b=>createHash('sha256').update(b).digest('hex'),textSha=b=>sha(b.toString().replaceAll('\r\n','\n'));
const {values}=parseArgs({options:{baseline:{type:'string',default:'b8c34de4'},repeats:{type:'string',default:'6'},output:{type:'string',default:'build/sreg-input-evidence.json'}}});
const repeats=Number(values.repeats);assert.ok(Number.isInteger(repeats)&&repeats>=4&&repeats<=16);
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:16*1024*1024});
const commit=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
mkdirSync(join(root,'build'),{recursive:true});const baseline=mkdtempSync(join(root,'build/sreg-input-baseline-'));
const candidate=mkdtempSync(join(root,'build/sreg-input-candidate-'));
const sources=git('ls-tree','-r','--name-only',commit,'web-player/lib').toString().trim().split('\n').filter(p=>p.endsWith('.js'));
for(const p of [...sources,'web-player/package.json','web-player/wasm/attiny13a.wasm','web-player/wasm/avr.wasm']){
  const bytes=git('show',commit+':'+p);
  for(const dir of [baseline,candidate]){mkdirSync(dirname(join(dir,p)),{recursive:true});writeFileSync(join(dir,p),bytes);}
  if(p.endsWith('.wasm'))assert.equal(sha(bytes),sha(read(p)),'Unchanged native runtime');
}
const patchPath='web-player/reports/sreg-inputs-20261026/candidate.patch',prefix=relative(root,candidate).replaceAll('\\','/');
assert.ok(prefix&&!isAbsolute(prefix)&&!prefix.startsWith('../'));
git('apply','--check','--directory='+prefix,patchPath);git('apply','--directory='+prefix,patchPath);
const regression='web-player/tests/avr-sreg-inputs.test.mjs';
const regressionSource='web-player/reports/sreg-inputs-20261026/structural-check.mjs';
for(const p of [regression,'web-player/tests/fixtures/attiny13a-system-firmware.mjs']){
  for(const dir of [baseline,candidate]){mkdirSync(dirname(join(dir,p)),{recursive:true});writeFileSync(join(dir,p),read(p===regression?regressionSource:p));}
}
function check(dir,label){
  const result=spawnSync(process.execPath,['--test',regression],{cwd:dir,encoding:'utf8',maxBuffer:8*1024*1024});
  assert.ifError(result.error);assert.ok([0,1].includes(result.status));
  writeFileSync(join(root,'build/sreg-input-'+label+'.tap'),result.stdout+result.stderr);
  return [...result.stdout.matchAll(/^(ok|not ok) \d+ - (.+)$/gm)].map(m=>({name:m[2],pass:m[1]==='ok'}));
}
const before=check(baseline,'before'),after=check(candidate,'after');
assert.equal(before.length,3);assert.equal(after.length,3);assert.equal(before.filter(t=>!t.pass).length,2);assert.ok(after.every(t=>t.pass));
const [{ATtiny13A:Old},{ATtiny13A:Current},oldCompiler,newCompiler]=await Promise.all([
  import(pathToFileURL(join(baseline,'web-player/lib/attiny13a.js')).href),import(pathToFileURL(join(candidate,'web-player/lib/attiny13a.js')).href),
  import(pathToFileURL(join(baseline,'web-player/lib/avr-transpiler.js')).href),import(pathToFileURL(join(candidate,'web-player/lib/avr-transpiler.js')).href)]);
const {AVR_CACHE_COMPILER_ID:candidateIdentity}=await import(pathToFileURL(join(candidate,'web-player/lib/avr-cache-identity.js')).href);
const native=read('web-player/wasm/attiny13a.wasm'),legacy=read('web-player/wasm/avr.wasm');
const fullExports=new WebAssembly.Instance(await WebAssembly.compile(native)).exports;
const legacyABI=newCompiler.runtimeABI(new WebAssembly.Instance(await WebAssembly.compile(legacy)).exports);
const fullABI=newCompiler.runtimeABI(fullExports),phaseABI=newCompiler.runtimeABI(fullExports,{resumable:true});
const catalogBytes=read('web-player/firmware.json'),catalog=JSON.parse(catalogBytes),sizes=[];
for(const entry of catalog.entries){
  const profile=resolveAVRProfile(entry.device),image=parseHex(entry.flashHex,profile.flashBytes);
  const modes=[['legacy',legacyABI,{}],...(profile.id==='attiny13a'?
    [['full',fullABI,{}],['resumable',phaseABI,{resumable:true}],['bounded-phase-locals',phaseABI,{resumable:true,boundedRegions:true,optimizePhaseLocals:true}]]:[])];
  for(const [mode,abi,policy] of modes){
    const options={device:profile.name,...policy},old=oldCompiler.transpileAVR(image,abi,options),current=newCompiler.transpileAVR(image,abi,options);
    assert.ok(WebAssembly.validate(current.bytes));if(!policy.resumable)assert.deepEqual(old.bytes,current.bytes,'Unchanged compatible code');
    assert.ok(current.bytes.length<=old.bytes.length);
    sizes.push({id:entry.id,mode,before:old.bytes.length,after:current.bytes.length,saved:old.bytes.length-current.bytes.length,sha256:sha(current.bytes)});
  }
}
const serialize=v=>JSON.stringify(v,(_k,x)=>typeof x==='bigint'?x.toString():x);
function capture(c,frames){
  const pcm=createHash('sha256'),pins=createHash('sha256'),architecture=createHash('sha256');let ms=0,pinCount=0;
  for(let n=0;n<frames;n+=256){
    const start=performance.now(),samples=c.capturePhysical(Math.min(256,frames-n),48000,c._testChannels);ms+=performance.now()-start;
    pcm.update(new Uint8Array(samples.buffer,samples.byteOffset,samples.byteLength));
    const trace=c.drainPinsPs();pinCount+=trace.length;pins.update(serialize(trace));
    for(const field of ['data','rom','eeprom'])architecture.update(c[field]);
    architecture.update(serialize({diagnostics:Array.from(c._state),pc:c.pc,cyc:c.cyc,timePs:c.state().timePs,retired:c.state().cpuPhase.retired}));
    assert.equal(c.state().deviceFault,0);
  }
  return {ms,pcm:pcm.digest('hex'),pins:pins.digest('hex'),architecture:architecture.digest('hex'),pinCount,irqs:c.state().irqs};
}
function same(a,b){for(const key of ['pcm','pins','architecture','pinCount','irqs'])assert.equal(a[key],b[key],key);}
const median=a=>{const s=[...a].sort((a,b)=>a-b),m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2;};
const results=[];
for(const id of ['rhythmic','lumiere-stereo'])for(const optimized of [false,true]){
  const entry=catalog.entries.find(e=>e.id===id),image=parseHex(entry.flashHex);
  const options={...nominalVerificationDeviceOptions(entry.cpuHz),cacheTranslation:false,
    ...(optimized?{fastBlocks:true,optimizeFlags:true,maxBlockInstructions:32,boundedRegions:true,optimizePhaseLocals:true}:{})};
  const runs=[];
  for(let trial=0;trial<repeats;trial++)for(const identity of trial%2?[true,false]:[false,true]){
    const cores=[Old,identity?Old:Current].map(Core=>new Core(image,null,options));
    for(const c of cores){c._testChannels=entry.audioChannels||1;c.observePins(63,{retainDuringAudio:true});}
    const order=trial%2?[1,0]:[0,1],warm=[],measured=[];
    for(const side of order)warm[side]=capture(cores[side],1024);same(...warm);
    for(const side of order)measured[side]=capture(cores[side],4096);same(...measured);
    assert.ok(measured[0].irqs>0);assert.ok(measured[0].pinCount>0);
    runs.push({trial,identity,order,beforeMs:measured[0].ms,afterMs:measured[1].ms,
      ratio:measured[0].ms/measured[1].ms,pcmSha256:measured[0].pcm,pinsSha256:measured[0].pins,
      architectureSha256:measured[0].architecture,pinCount:measured[0].pinCount,irqs:measured[0].irqs});
  }
  const summarize=identity=>{const ratios=runs.filter(r=>r.identity===identity).map(r=>r.ratio);return {median:median(ratios),min:Math.min(...ratios),max:Math.max(...ratios)};};
  const result={id,policy:optimized?'bounded-phase-locals':'verification',warmupFrames:1024,frames:4096,rate:48000,
    paired:summarize(false),identity:summarize(true),runs};results.push(result);
  console.log(JSON.stringify({id,policy:result.policy,paired:result.paired,identity:result.identity}));
}
const report={schema:'micromusic-sreg-inputs-v1',baselineCommit:commit,compilerIdentity:candidateIdentity,productionCompilerIdentity:AVR_CACHE_COMPILER_ID,
  sourceSha256:textSha(readFileSync(join(candidate,'web-player/lib/avr-transpiler.js'))),baselineSourceSha256:textSha(git('show',commit+':web-player/lib/avr-transpiler.js')),
  candidatePatchSha256:textSha(read(patchPath)),harnessSha256:textSha(readFileSync(fileURLToPath(import.meta.url))),regressionSha256:textSha(read(regressionSource)),catalogSha256:textSha(catalogBytes),
  native:{bytes:native.length,sha256:sha(native)},node:process.version,v8:process.versions.v8,
  methodology:'Serial main-thread pairs with balanced side/control order; fresh chips, equal warmups. Capture calls timed; construction, hashes, snapshots and explicit pin drains excluded. No Workers or overlapping teardown.',
  hardwareTested:false,realtimeTested:false,before,after,sizes,results};
mkdirSync(dirname(join(root,values.output)),{recursive:true});writeFileSync(join(root,values.output),JSON.stringify(report,null,2)+'\n');
