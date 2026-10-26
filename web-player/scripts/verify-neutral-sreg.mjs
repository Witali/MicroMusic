// Reproduce the SREG regression and static emitted-size evidence. No timings.
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,mkdtempSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync,spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {parseArgs} from 'node:util';
import {parseHex} from '../lib/hex.js';
import {resolveAVRProfile} from '../lib/avr-profiles.js';
import {nominalVerificationDeviceOptions} from '../lib/emulation-configurations.js';
import {AVR_CACHE_COMPILER_ID} from '../lib/avr-cache-identity.js';
const root=fileURLToPath(new URL('../../',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex');
const read=p=>readFileSync(join(root,p));
const {values}=parseArgs({options:{baseline:{type:'string',default:'23c4b7b2'},output:{type:'string',default:'build/neutral-sreg-evidence.json'}}});
const git=(...args)=>execFileSync('git',args,{cwd:root,maxBuffer:16*1024*1024});
const commit=git('rev-parse','--verify',values.baseline+'^{commit}').toString().trim();
mkdirSync(join(root,'build'),{recursive:true});
const baseline=mkdtempSync(join(root,'build/neutral-sreg-baseline-'));
const sources=git('ls-tree','-r','--name-only',commit,'web-player/lib').toString().trim().split('\n').filter(p=>p.endsWith('.js'));
for(const p of [...sources,'web-player/package.json','web-player/wasm/attiny13a.wasm','web-player/wasm/avr.wasm']){
  const bytes=git('show',commit+':'+p);mkdirSync(dirname(join(baseline,p)),{recursive:true});writeFileSync(join(baseline,p),bytes);
  if(p.endsWith('.wasm'))assert.equal(sha(bytes),sha(read(p)),'Unchanged native runtime');
}
const regression='web-player/tests/avr-neutral-sreg.test.mjs';
for(const p of [regression,'web-player/tests/fixtures/attiny13a-system-firmware.mjs']){
  mkdirSync(dirname(join(baseline,p)),{recursive:true});writeFileSync(join(baseline,p),read(p));
}
function check(dir,label){
  const result=spawnSync(process.execPath,['--test',regression],{cwd:dir,encoding:'utf8',maxBuffer:8*1024*1024});
  assert.ifError(result.error);assert.ok([0,1].includes(result.status));
  writeFileSync(join(root,'build/neutral-sreg-'+label+'.tap'),result.stdout+result.stderr);
  return [...result.stdout.matchAll(/^(ok|not ok) \d+ - (.+)$/gm)].map(m=>({name:m[2],pass:m[1]==='ok'}));
}
const before=check(baseline,'before'),after=check(root,'after');
assert.equal(before.length,26);assert.equal(after.length,26);assert.equal(before.filter(t=>!t.pass).length,19);
assert.ok(after.every(t=>t.pass));assert.deepEqual(before.map(t=>t.name),after.map(t=>t.name));
const [oldCompiler,newCompiler]=await Promise.all([
  import(pathToFileURL(join(baseline,'web-player/lib/avr-transpiler.js')).href),import('../lib/avr-transpiler.js')]);
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
    assert.ok(WebAssembly.validate(old.bytes));assert.ok(WebAssembly.validate(current.bytes));
    assert.ok(current.bytes.length<=old.bytes.length,entry.id+' / '+mode);
    sizes.push({id:entry.id,mode,before:old.bytes.length,after:current.bytes.length,saved:old.bytes.length-current.bytes.length,
      beforeSha256:sha(old.bytes),afterSha256:sha(current.bytes)});
  }
}
const [{ATtiny13A:Old},{ATtiny13A:Current}]=await Promise.all([
  import(pathToFileURL(join(baseline,'web-player/lib/attiny13a.js')).href),import('../lib/attiny13a.js')]);
const audio=[];
for(const id of ['rhythmic','lumiere-stereo'])for(const optimized of [false,true]){
  const entry=catalog.entries.find(e=>e.id===id);assert.ok(entry,id);
  const options={...nominalVerificationDeviceOptions(entry.cpuHz),cacheTranslation:false,
    ...(optimized?{fastBlocks:true,optimizeFlags:true,maxBlockInstructions:32,boundedRegions:true,optimizePhaseLocals:true}:{})};
  const image=parseHex(entry.flashHex),cores=[Old,Current].map(Core=>new Core(image,null,options));
  for(const c of cores)c.observePins(63,{retainDuringAudio:true});
  const pcm=createHash('sha256'),pins=createHash('sha256');let pinCount=0;
  for(let chunk=0;chunk<16;chunk++){
    const samples=cores.map(c=>c.capturePhysical(256,48000,entry.audioChannels||1));assert.deepEqual(...samples);
    pcm.update(new Uint8Array(samples[0].buffer,samples[0].byteOffset,samples[0].byteLength));
    const traces=cores.map(c=>c.drainPinsPs());assert.deepEqual(...traces);pinCount+=traces[0].length;
    pins.update(JSON.stringify(traces[0],(_k,v)=>typeof v==='bigint'?v+'n':v));
    assert.deepEqual(cores[0].data,cores[1].data);assert.deepEqual(cores[0].eeprom,cores[1].eeprom);
    assert.deepEqual(cores[0].rom,cores[1].rom);assert.deepEqual(Array.from(cores[0]._state),Array.from(cores[1]._state));
    for(const field of ['pc','cyc'])assert.equal(cores[0][field],cores[1][field]);
    for(const c of cores)assert.equal(c.state().deviceFault,0);
    assert.equal(cores[0].state().cpuPhase.retired,cores[1].state().cpuPhase.retired);
    assert.equal(cores[0].state().timePs,cores[1].state().timePs);
  }
  const state=cores[1].state();assert.ok(state.irqs>0);assert.ok(pinCount>0);
  audio.push({id,policy:optimized?'bounded-phase-locals':'verification',frames:4096,sampleRate:48000,
    pcmSha256:pcm.digest('hex'),pinsSha256:pins.digest('hex'),pinCount,irqs:state.irqs,
    retired:state.cpuPhase.retired.toString(),timePs:state.timePs.toString()});
}
const report={schema:'micromusic-neutral-sreg-v1',baselineCommit:commit,compilerIdentity:AVR_CACHE_COMPILER_ID,
  sourceSha256:sha(read('web-player/lib/avr-transpiler.js').toString().replaceAll('\r\n','\n')),
  baselineSourceSha256:sha(git('show',commit+':web-player/lib/avr-transpiler.js').toString().replaceAll('\r\n','\n')),
  harnessSha256:sha(readFileSync(fileURLToPath(import.meta.url),'utf8').replaceAll('\r\n','\n')),
  regressionSha256:sha(read(regression).toString().replaceAll('\r\n','\n')),catalogSha256:sha(catalogBytes),
  native:{bytes:native.length,sha256:sha(native)},node:process.version,v8:process.versions.v8,
  hardwareTested:false,realtimeTested:false,executionSpeedMeasured:false,
  tests:after.map((t,i)=>({name:t.name,before:before[i].pass,after:t.pass})),sizes,audio};
mkdirSync(dirname(join(root,values.output)),{recursive:true});writeFileSync(join(root,values.output),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({before:{pass:7,fail:19},after:{pass:26,fail:0},artifacts:sizes.length,
  savedBytes:{min:Math.min(...sizes.map(s=>s.saved)),max:Math.max(...sizes.map(s=>s.saved))}},null,2));
