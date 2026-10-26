import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const json=v=>JSON.stringify(v,(_,n)=>typeof n==='bigint'?n.toString():n);
const sha=b=>createHash('sha256').update(b).digest('hex'),hash=v=>sha(json(v));
const read=name=>readFileSync(new URL(name,import.meta.url),'utf8').replaceAll('\r\n','\n');
const report=JSON.parse(read('browser.json')),sources=JSON.parse(read('sources.json'));
const root=fileURLToPath(new URL('../../../',import.meta.url));
assert.equal(report.schema,'micromusic-bounded-browser-v1');
for(const flag of ['complete','parityComplete','realtimeComplete'])assert.equal(report[flag],true);
for(const [path,digest]of Object.entries(report.sourceSha256)){
  assert.equal(sha(sources[path]),digest,path);
  assert.equal(execFileSync('git',['show','ee25c4c:'+path],{cwd:root,encoding:'utf8'}).replaceAll('\r\n','\n'),sources[path],path+' retained revision');
}
const archivedRuntime=execFileSync('git',['show','ee25c4c:web-player/wasm/attiny13a.wasm'],{cwd:root,maxBuffer:1024*1024});
assert.equal(sha(archivedRuntime),report.runtimeSha256);
assert.equal(report.runtimeSha256,'111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6');
const ids=['rhythmic','lumiere-stereo','hq4-chego-tiny'];assert.deepEqual(report.parity.map(r=>r.id),ids);
assert.equal(report.audio.length,6);assert.equal(report.sampleRate,48000);assert.equal(report.audioDurationMs,10000);
const snapshot=c=>({state:c.state(),diagnostics:Array.from(c._state),data:Array.from(c.data),eeprom:Array.from(c.eeprom),flash:Array.from(c.rom),irq:Array.from(c.irqFrames)});
let checkpoints=0,replayCheckpoints=0;
for(const row of report.parity){assert.equal(row.checkpoints.length,4);assert.ok(row.irqCount>0);checkpoints+=row.checkpoints.length;}
if(process.argv.includes('--replay')){
const [{ATtiny13A,runtimeModule},{createPackage},{createRenderer},{parseHex}]=await Promise.all([
  import('../../lib/attiny13a.js'),import('../../lib/attiny13a-package.js'),import('../../lib/engines.js'),import('../../lib/hex.js')]);
const runtime=readFileSync(new URL('../../wasm/attiny13a.wasm',import.meta.url));assert.equal(sha(runtime),report.runtimeSha256);
const environment=JSON.parse(read('environment.json'));
for(const [path,digest]of Object.entries(environment.sourceCatalogSha256))
  assert.equal(sha(readFileSync(new URL('../../../'+path,import.meta.url),'utf8').replaceAll('\r\n','\n')),digest,path);
const catalogs=['firmware','hq4-firmware'].flatMap(n=>JSON.parse(readFileSync(new URL('../../'+n+'.json',import.meta.url))).entries);
for(const row of report.parity){
  const entry=catalogs.find(e=>e.id===row.id),flash=parseHex(entry.flashHex),eeprom=entry.eepromHex?parseHex(entry.eepromHex,64):undefined;
  assert.equal(sha(flash),row.flashSha256);assert.equal(row.checkpoints.length,4);assert.ok(row.irqCount>0);
  const hz=entry.cpuHz||9600000,osccalHz=Array(128).fill(0);osccalHz[0]=hz;
  const configuration={resumable:true,oscillatorHz:hz,osccalHz,nvmClockProfile:1,nvmCalibrationReferenceHz:hz};
  const pairs=[];
  for(const [index,boundedRegions]of [false,true].entries()){
    const c=new ATtiny13A(flash,eeprom,{...configuration,boundedRegions,runtimeModule});assert.equal(sha(c.transpiledBytes),row.cpuSha256[index]);
    const pkg=await createPackage({flash,eeprom,runtime,translated:c.transpiledBytes,configuration});
    pairs.push(await createRenderer({...entry,devicePackage:pkg},48000,{cutoff:9000,volume:.65},'device'));
  }
  for(const expected of row.checkpoints){
    for(const renderer of pairs){
      const pcm=renderer.render(1024),pins=renderer.core.drainPinsPs();
      assert.equal(sha(pcm),expected.pcmSha256,row.id+' Node/browser filtered PCM');
      assert.equal(hash(snapshot(renderer.core)),expected.stateSha256,row.id+' Node/browser complete state');
      assert.equal(hash(pins),expected.pinsSha256,row.id+' Node/browser pins');
      assert.equal(renderer.core.state().deviceFault,0);
    }
    replayCheckpoints+=2;
  }
}
}
const seen=new Set();
for(const row of report.audio){
  const key=row.id+'/'+row.boundedRegions;assert.ok(ids.includes(row.id));assert.equal(typeof row.boundedRegions,'boolean');
  assert.ok(!seen.has(key));seen.add(key);assert.equal(row.sampleRate,48000);
  assert.ok(row.positions.length>100);assert.ok(row.states.length>10);assert.equal(row.error,undefined);
  assert.ok(row.wallMs>=10000&&row.wallMs<12000);assert.ok(row.contextMs>=9000);assert.equal(row.contextState,'running');
  assert.equal(row.visibilityStart,'visible');assert.equal(row.visibilityEnd,'visible');assert.ok(row.visibilityChanges.every(v=>v==='visible'));
  assert.ok(row.contextEvents.every(e=>e.state==='running'));assert.ok(row.lastPositionAgeMs<250);
  assert.deepEqual(row.last,row.positions.at(-1));assert.ok(row.maximumIRQs>0);assert.ok(row.states.every(s=>s.deviceFault===0));
  let frames=0,clock=0,underruns=0;
  for(const p of row.positions){
    assert.ok(p.frames>=frames&&p.clockFrames>=clock&&p.underruns>=underruns);assert.ok(p.frames<=p.clockFrames);
    assert.ok(p.buffered>=0&&p.buffered<=32768);frames=p.frames;clock=p.clockFrames;underruns=p.underruns;
  }
  assert.ok(underruns>0);assert.ok(frames<clock);assert.equal(row.accepted,false);
}
assert.equal(report.realtimeAccepted,false);
const recorded=JSON.parse(read('node-replay.json'));assert.equal(recorded.browserParityCheckpoints,12);
assert.equal(recorded.nodeReplayCheckpoints,24);assert.equal(recorded.realtimeAccepted,false);
assert.deepEqual(recorded.rows,report.audio.map(r=>({id:r.id,boundedRegions:r.boundedRegions,
  underruns:r.last.underruns,deliveredPercent:100*r.last.frames/r.last.clockFrames})));
console.log(JSON.stringify({browserParityCheckpoints:checkpoints,nodeReplayCheckpoints:replayCheckpoints,audioRuns:6,
  audioSeconds:60,realtimeAccepted:false,rows:report.audio.map(r=>({id:r.id,boundedRegions:r.boundedRegions,
    underruns:r.last.underruns,deliveredPercent:100*r.last.frames/r.last.clockFrames}))}));
