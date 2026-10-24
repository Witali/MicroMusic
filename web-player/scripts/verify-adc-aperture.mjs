// Synthetic sensitivity experiment only. Executes the actual assembled probe
// binaries and decodes their wire-v2 bytes. Supplies no silicon observations.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {mkdirSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {dirname,join,relative,resolve} from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {ATtiny13A} from '../lib/attiny13a.js';

const root=new URL('../../',import.meta.url),rootPath=fileURLToPath(root),args=process.argv.slice(2),cli={};
while(args.length){
 const name=args.shift();
 if(!['--input','--out'].includes(name)||!args.length)throw Error('Usage: verify-adc-aperture.mjs [--input VERIFICATION_DIR] [--out JSON_FILE]');
 cli[name]=args.shift();
}
const input=resolve(cli['--input']??join(rootPath,'build/hardware-probe-verification'));
const output=resolve(cli['--out']??join(rootPath,'build/adc-aperture-sensitivity.json'));
const psPerUs=1000000n,cpuPeriodPs=125000n;
const quantumPs=8n*psPerUs,limitPs=25000n*psPerUs;
const restoreAfterPs=1000n*psPerUs;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const file=path=>readFileSync(new URL(path,root));
const profiles=['first-conversion','normal-conversion-control'];
const descriptor=JSON.parse(file('web-player/native/peripherals/adc-probe.json'));
const verification=JSON.parse(readFileSync(join(input,'summary.json')));
const verified=verification.probes.find(probe=>probe.name==='adc');
assert.ok(verified,'Run verify-hardware-probes.mjs with ADC selected first');
assert.equal(verified.sourceSha256,hash(file('web-player/native/peripherals/adc-probe.S')),'Reverify changed source');
assert.equal(verified.configurationSha256,hash(file('web-player/native/peripherals/adc-probe.json')),'Reverify changed profile');
assert.equal(verification.runtimeSha256,hash(file('web-player/wasm/attiny13a.wasm')),'Reverify changed native runtime');
// Include a late step as a negative control after the distinguishing window.
const firstOffsetsUs=[110,112,114,116,118,120,122,124,126];
const firmware=Object.fromEntries(profiles.map(profile=>{
 const path=join(input,'adc',profile+'.bin'),binary=readFileSync(path),sha256=hash(binary);
 assert.equal(sha256,verified.profiles.find(record=>record.id===profile).imageSha256,'Use the verified canonical image');
 return[profile,{path:relative(rootPath,path).replaceAll('\\','/'),binary,sha256,
  profileId:descriptor.profiles.find(record=>record.id===profile).profileId}];
}));
const options={resumable:true,fastIdle:false,oscillatorHz:8000000,
 vccMicrovolts:5000000,watchdogHz:128000,fuseLow:0x70,fuseHigh:0xff,lock:0xff,fuseStartupProfile:1,
 clkiProfile:{phasePolicy:'digital-noninverting-zero-seed-v1',initialLevel:1}};

function run(profile,adcFirstSample,offsetUs,direction){
 const [initialUv,steppedUv]=direction==='rising'?[1000000,4000000]:[4000000,1000000];
 const cpu=new ATtiny13A(firmware[profile].binary,null,{...options,adcFirstSample});
 assert.equal(cpu.injectClkiPeriodicPs({startPs:0n,initialLevel:1,
  highPs:62500n,lowPs:62500n,transitionCount:limitPs/62500n,knownUntilPs:limitPs}),true);
 cpu.setAnalogPs({at:0n,pin:2,microvolts:initialUv});
 let previous=cpu.state().pins.levels,partial=0,bitCount=0,byteCount=0;
 const frames=[],wire=[],markers=[],injections=[];
 function drain(){
  const observedAt=cpu.state().timePs;
  for(const event of cpu.drainPinsPs()){
   const changed=previous^event.levels;
   if(changed&1){
    if(event.levels&1){
     const at=event.timePs+BigInt(offsetUs)*psPerUs;
     const restore=at+restoreAfterPs;
     assert.ok(at>observedAt,'Marker must be observed before the scheduled step');
     cpu.setAnalogPs({at,pin:2,microvolts:steppedUv});
     cpu.setAnalogPs({at:restore,pin:2,microvolts:initialUv});
     injections.push({trial:markers.length+1,markerRisePs:event.timePs,
      markerObservedAtPs:observedAt,stepPs:at,restoreBaselinePs:restore});
     markers.push({risePs:event.timePs});
    }else{
     assert.ok(markers.length,'Falling marker must have a preceding rise');
     markers.at(-1).fallPs=event.timePs;
    }
   }
   if((changed&2)&&(event.levels&2)){
    partial=(partial<<1)|Number(!!(event.levels&16));bitCount++;
    if(bitCount===8){wire.push(partial);partial=0;bitCount=0;byteCount++;}
    if(byteCount===14){
     const bytes=wire.splice(0);byteCount=0;
     assert.deepEqual(bytes.slice(0,2),[0xa5,0x5a]);
     const payload=bytes.slice(2,13);
     assert.equal(payload.reduce((a,b)=>a^b,0),bytes[13]);
     assert.equal(payload[0],2,'Wire version');assert.equal(payload[1],3,'ADC probeId');
     assert.equal(payload[2],firmware[profile].profileId,'Build profile identity');
     const sequence=payload[3]|(payload[4]<<8),data=payload.slice(5);
     assert.equal(sequence,frames.length,'Consecutive boot and trial records');
     assert.equal(data[4]&128,0,'ADC interrupts must not be accepted');
     frames.push({frameEndPs:event.timePs,bytes,sequence,profileId:payload[2],data,
      adcCode:sequence?(data[0]|(data[1]<<8)):null});
    }
   }
   previous=event.levels;
  }
 }
 drain();
 while(frames.length<3&&cpu.state().timePs<limitPs){
  const now=cpu.state().timePs,end=now+quantumPs<limitPs?now+quantumPs:limitPs;
  cpu.runUntilPs(end);drain();assert.equal(cpu.state().deviceFault,0);
 }
 assert.equal(frames.length,3,'Boot plus the actual two measured trial frames');
 assert.equal(markers.length,2);assert.equal(bitCount,0);assert.equal(wire.length,0);
 for(const [index,frame] of frames.slice(1).entries()){
  assert.equal(frame.data[5],1,'Actual conversion record, not a boot/control');
  assert.equal(frame.data[3]&0x70,0x10,'ADIF set, ADSC/ADATE clear at completion');
  assert.ok(markers[index].fallPs>=markers[index].risePs);
 }
 return {profile,adcFirstSample,offsetUs,direction,initialUv,steppedUv,frames,markers,injections,
  translatedWasmSha256:hash(cpu.transpiledBytes),
  translationManifestSha256:hash(JSON.stringify(cpu.transpilation)),
  measuredCodes:frames.slice(1).map(frame=>frame.adcCode),
  finishedAtPs:cpu.state().timePs,deviceFault:cpu.state().deviceFault};
}

const runs=[];
for(const direction of ['rising','falling'])for(const offsetUs of firstOffsetsUs)for(const phase of [27,29]){
 const result=run('first-conversion',phase,offsetUs,direction);runs.push(result);
}
for(const direction of ['rising','falling'])for(const phase of [27,29]){
 const result=run('normal-conversion-control',phase,120,direction);runs.push(result);
}
const comparisons=['rising','falling'].flatMap(direction=>firstOffsetsUs.map(offsetUs=>{
 const pair=runs.filter(run=>run.profile==='first-conversion'&&run.offsetUs===offsetUs&&run.direction===direction);
 const [a,b]=pair.map(run=>run.measuredCodes);
 const low=direction==='rising'?204:819,high=direction==='rising'?819:204;
 const expected=offsetUs<=116?[high,high]:offsetUs>=126?[low,low]:[low,high];
 assert.deepEqual(a,[expected[0],expected[0]],'Configured phase27 synthetic window');
 assert.deepEqual(b,[expected[1],expected[1]],'Configured phase29 synthetic window');
 return {offsetUs,direction,codes27:a,codes29:b,distinguishes:a.some((code,i)=>code!==b[i])};
}));
const normal=runs.filter(run=>run.profile==='normal-conversion-control');
for(const run of normal)assert.deepEqual(run.measuredCodes,run.direction==='rising'?[204,204]:[819,819]);
const normalInsensitive=true; // Both configured choices passed the explicit plateau controls above.
const librarySourceSha256={};
const scan=folder=>{for(const entry of readdirSync(folder,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name))){
 const path=join(folder,entry.name);if(entry.isDirectory())scan(path);
 else if(entry.isFile()&&entry.name.endsWith('.js'))librarySourceSha256[relative(rootPath,path).replaceAll('\\','/')]=hash(readFileSync(path));
}};
scan(join(rootPath,'web-player/lib'));
const report={schema:'micromusic-adc-aperture-sensitivity-v1',status:'synthetic-fixture',
 siliconResults:false,rootHead:execFileSync('git',['rev-parse','HEAD'],{cwd:fileURLToPath(root),encoding:'utf8'}).trim(),
 inputs:{runtimeSha256:hash(file('web-player/wasm/attiny13a.wasm')),
  harnessSha256:hash(readFileSync(fileURLToPath(import.meta.url))),
  descriptorSha256:hash(file('web-player/native/peripherals/adc-probe.json')),
  sourceSha256:hash(file('web-player/native/peripherals/adc-probe.S')),
  wireSha256:hash(file('web-player/native/peripherals/probe-wire.inc')),
  registerDefinitionsSha256:hash(file('web-player/native/attiny13a-registers.generated.inc')),
  librarySourceSha256,
  firmware:Object.fromEntries(profiles.map(p=>[p,{path:firmware[p].path,sha256:firmware[p].sha256}])),
  options,clock:{frequencyHz:8000000,highPs:'62500',lowPs:'62500',cpuPeriodPs:cpuPeriodPs.toString()},
  analog:{channel:1,pin:'PB2',levelsMicrovolts:[1000000,4000000],directions:['rising','falling'],
   model:'ideal instantaneous voltage injection; no analog settling/noise model',restoreAfterPs:restoreAfterPs.toString()},
  quantumPs:quantumPs.toString(),limitPs:limitPs.toString(),trialsPerRun:2},
 comparisons,normalInsensitive,runs,
 interpretation:{firstFirmwareSensitive:comparisons.some(c=>c.distinguishes),
  nominal112UsDistinguishes:comparisons.filter(c=>c.offsetUs===112).some(c=>c.distinguishes),
  proven:'Actual assembled ADC probe records distinguish configured digital sample phases at the listed ideal stimulus offsets. Normal warmed control is compared separately.',
  notProven:'No silicon aperture, actual analog settling, clock-to-pad timing, ADIF bit-operation outcome or preferred default is established. Wire frame times are transport times, not sample times.'}};
mkdirSync(dirname(output),{recursive:true});
writeFileSync(output,JSON.stringify(report,
 (_key,value)=>typeof value==='bigint'?value.toString():value,2)+'\n');
console.log(JSON.stringify({firstFirmwareSensitive:report.interpretation.firstFirmwareSensitive,
 normalInsensitive,runs:runs.length,trials:runs.length*2,
 distinguishingOffsetsUs:[...new Set(comparisons.filter(c=>c.distinguishes).map(c=>c.offsetUs))]}));
console.log(output);
