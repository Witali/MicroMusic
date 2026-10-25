// Independent runtime/IRQ smoke and C/ASM conformance on both retained boards.
// C is an arithmetic fallback; report throughput failures separately from PCM.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {AVRCore} from '../web-player/lib/avr-core.js';
import {UniversalReference} from './universal-reference.mjs';

const root=fileURLToPath(new URL('../',import.meta.url));
const absolute=p=>path.resolve(root,p),readJSON=p=>JSON.parse(fs.readFileSync(absolute(p)));
const sha=b=>createHash('sha256').update(b).digest('hex');
const word=(data,at)=>data[at]|data[at+1]<<8;
const option=(name,fallback)=>process.argv.find(arg=>arg.startsWith('--'+name+'='))?.slice(name.length+3)||fallback;
const reportPath=option('report','ATtiny88/Music/universal/reports/backend-all-boards.json');
const snapshotDirectory=option('snapshot-dir','build/backend-all-boards');
const profiles=[
 {name:'ASM8',directory:option('asm8-dir','ATtiny88/Music/universal/songs'),backend:'avr-asm',cpuHz:8000000},
 {name:'C8',directory:option('c8-dir','build/universal/c'),backend:'c',cpuHz:8000000},
 {name:'ASM16',directory:option('asm16-dir','ATtiny88/Music/universal/songs-micronucleus'),backend:'avr-asm',cpuHz:16000000},
 {name:'C16',directory:option('c16-dir','build/universal/c16-check'),backend:'c',cpuHz:16000000},
].map(profile=>{
 const folder=profile.directory+'/lumiere-stereo',meta=readJSON(folder+'/build-report.json');
 const rom=fs.readFileSync(absolute(folder+'/synth.bin')),score=readJSON(folder+'/score.json');
 assert.equal(meta.cpuHz,profile.cpuHz);assert.equal(meta.backend,profile.backend);
 assert.equal(meta.renderABI,'packed-stereo-u32');assert.equal(meta.pwmBufferBytes,192);
 assert.equal(meta.channels,2);assert.equal(sha(rom),meta.flashSha256);
 assert.equal(sha(rom.subarray(0,meta.engineBytes)),meta.engineSha256);
 assert.ok(meta.sourceInputs,'Fresh build reports must identify their compiled sources');
 for(const [file,hash] of Object.entries(meta.sourceInputs))
  assert.equal(sha(fs.readFileSync(absolute(file),'utf8').replaceAll('\r\n','\n')),hash,
   profile.name+': rebuild after source change in '+file);
 return {...profile,folder,meta,rom,score};
});
const input=profile=>({name:profile.name,cpuHz:profile.cpuHz,backend:profile.backend,
 romPath:profile.folder+'/synth.bin',flashSha256:sha(profile.rom),engineSha256:profile.meta.engineSha256,
 engineBytes:profile.meta.engineBytes,flashBytes:profile.rom.length,
 buildReportSha256:sha(fs.readFileSync(absolute(profile.folder+'/build-report.json'))),
 toolchainVersion:profile.meta.toolchainVersion,
 compiledSourceTextLfSha256:profile.meta.sourceInputs,
 scoreSha256:sha(fs.readFileSync(absolute(profile.folder+'/score.json')))});

function smoke(profile){
 const {name,meta,rom,score}=profile;
 const c=new AVRCore(rom,null,{target:'attiny88',cpuHz:meta.cpuHz});
 const ref=new UniversalReference(score,meta.cpuHz,{pwmChannels:2,pwmFrames:96,pwmReserveFrames:4});
 if(meta.cpuHz===16000000){c.sp=0x17f;c.data[c.profile.system.mcusr]=8;c.data[c.profile.system.wdt]=0x2b;}
 const address=n=>meta.labels[n]-0x800000,read=address('um_read'),write=address('um_write'),ring=address('um_ring');
 const render=meta.labels.um_render/2,irq=meta.labels['__vector_'+c.profile.timer.vector]/2;
 const returns=new Set(),retis=new Set();
 for(let pc=0;pc<meta.engineBytes/2;pc++){
  if(c.op[pc]===6&&pc+1+c.k[pc]===render)returns.add(pc+1);
  if(c.op[pc]===4)retis.add(pc);
 }
 assert.ok(returns.size);for(const p of [render,irq,...returns,...retis])c.batch[p]=0;
 let expected=0,lastWrite=ref.write,output=[128,128],samples=0,irqs=0,minQueued=96,failure=null;
 try{while(c.cyc<meta.cpuHz){
  if(!c.inIRQ&&c.pc===render){
   assert.equal(c.data[write],ref.write,name+': committed frames');
   if(ref.samples)for(let i=0;i<8;i++)
    assert.equal(c.data[ring+(lastWrite+i)%192],ref.ring[(lastWrite+i)%192],name+': interpolated PCM');
   lastWrite=ref.write;expected=ref.beginSample();
  }else if(!c.inIRQ&&returns.has(c.pc)){
   assert.equal((c.r[22]|c.r[23]<<8|c.r[24]<<16|c.r[25]<<24)>>>0,expected,name+': exact stereo mix');
   ref.finishSample();samples++;
  }else if(c.pc===irq){
   const consumer=c.data[read],queued=((c.data[write]-consumer+192)%192)/2;
   assert.ok(queued>0,name+': FIFO underrun');minQueued=Math.min(minQueued,queued);
   output=[ref.ring[consumer],ref.ring[consumer+1]];irqs++;
  }else if(c.inIRQ&&retis.has(c.pc))
   assert.deepEqual([word(c.data,c.profile.timer.ocra),word(c.data,c.profile.timer.ocrb)],output,name+': exact stereo PWM');
  if(!c.runBlock())c.step();
 }}catch(error){failure=error.message;}
 const underrun=!!failure?.includes('FIFO underrun');
 assert.ok(!failure||underrun,name+': '+failure);
 if(profile.backend==='avr-asm')assert.equal(failure,null,name+': published profile must complete the second');
 if(!failure)assert.equal(c.data[address('um_underruns')],0);
 assert.equal(c.lost,0);assert.equal(c.workLost,0);assert.ok(c.minSP>=ring+192);
 const result={...input(profile),completedSecond:!failure,exactMixAndPwmUntilStop:true,
  simulatedSeconds:c.cyc/meta.cpuHz,samples,stereoIRQs:irqs,minimumQueuedFrames:minQueued,
  stackMarginBytes:c.minSP-ring-192,firstUnderrunSeconds:underrun?c.cyc/meta.cpuHz:null,
  ...(failure?{failure}:{})};
 console.log(JSON.stringify(result));return result;
}

const dfp='ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/atdf/ATtiny88.atdf';
const registers=new Map([...fs.readFileSync(absolute(dfp),'utf8').matchAll(/<register\b([^>]+)>/g)].map(match=>{
 const attributes=Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(x=>[x[1],x[2]]));
 return [attributes.name,Number(attributes.offset)];
}));
const io=name=>{assert.ok(registers.has(name),name);return registers.get(name);};
function startup(profile){
 const {meta,rom}=profile,c=new AVRCore(rom,null,{target:'attiny88',cpuHz:meta.cpuHz,fastBlocks:false});
 const inherited={PRR:0xad,EIMSK:3,PCICR:15,TIMSK0:7,TIMSK1:1,TCCR0A:0xff,TCCR1A:0xa1,
  TCCR1B:9,GTCCR:0x80,ADCSRA:0x8f,ACSR:8,SPCR:0xff,TWCR:0xff,EECR:4,SMCR:7,
  DDRB:0xff,PORTB:0xff,MCUSR:8,WDTCSR:0x2b};
 for(const [name,value] of Object.entries(inherited))c.data[io(name)]=value;
 c.sp=0x17f;
 const gated=['TIMSK0','TIMSK1','TCCR0A','TCCR1A','TCCR1B','ADCSRA','SPCR','TWCR'];
 const start=meta.labels.um_board_reset/2,end=meta.labels.__do_clear_bss/2;
 assert.ok(start<end);let entered=false,steps=0;
 while(c.pc!==end){
  assert.ok(steps++<2000,'Bounded early startup');
  if(c.pc===start){entered=true;assert.equal(c.sp,767);assert.equal(c.sreg&128,0);}
  const before=gated.map(name=>c.data[io(name)]),prr=c.data[io('PRR')];
  if(c.pc>=start&&c.pc<end){
   const instruction=word(rom,c.pc*2);
   assert.ok((instruction&0xf000)!==0xd000&&(instruction&0xfe0e)!==0x940e&&
    instruction!==0x9508&&instruction!==0x9518,'Naked .init3 must fall through without calls or returns');
  }
  c.step();gated.forEach((name,i)=>{if(before[i]!==c.data[io(name)])assert.equal(prr,0,name+': clear PRR before accessing gated I/O');});
 }
 assert.ok(entered);assert.equal(c.sp,767);assert.equal(c.r[1],0);assert.equal(c.sreg&128,0);
 for(const name of [...Object.keys(inherited),'CLKPR'])assert.equal(c.data[io(name)],0,'Initialized '+name);
 return {...input(profile),passed:true,steps,registersResolvedFrom:dfp,stackBeforeBss:767,
  prrBeforeGatedCleanup:true,protectedWatchdogDisabled:true,nakedFallThrough:true};
}

let interpolationPairs=0;
for(let previous=0;previous<256;previous++)for(let target=0;target<256;target++){
 const mid=(previous+target)>>1;
 assert.deepEqual(Array.from({length:4},(_,i)=>Math.floor(((3-i)*previous+(i+1)*target)/4)),
  [(previous+mid)>>1,mid,(mid+target)>>1,target]);interpolationPairs++;
}
const startupChecks=profiles.filter(p=>p.cpuHz===16000000).map(startup);
const smokeChecks=profiles.map(smoke),conformance=[];
for(const cpuHz of [8000000,16000000]){
 const directory=absolute(path.join(snapshotDirectory,String(cpuHz)));fs.mkdirSync(directory,{recursive:true});
 for(const profile of profiles.filter(p=>p.cpuHz===cpuHz)){
  const stem=path.join(directory,'engine-'+profile.backend);
  fs.writeFileSync(stem+'.bin',profile.rom.subarray(0,profile.meta.engineBytes));
  fs.writeFileSync(stem+'.json',JSON.stringify(profile.meta));
 }
 const output=path.join(directory,'backend-verification.json');
 const child=spawnSync(process.execPath,['tools/test-universal-backends.mjs','--engine-dir='+directory,'--report='+output],
  {cwd:root,encoding:'utf8'});
 assert.equal(child.status,0,child.stderr||child.stdout);console.log(child.stdout.trim());
 conformance.push({cpuHz,...JSON.parse(fs.readFileSync(output))});
}
const sources=['ATtiny88/Music/universal/engine.c','ATtiny88/Music/universal/engine.h',
 'ATtiny88/Music/universal/render-avr.S','ATtiny88/Music/universal/irq-avr.S',
 'ATtiny88/Music/universal/platform.c','ATtiny88/Music/universal/audio-buffer.h',
 'ATtiny88/Music/universal/clock.h','ATtiny88/Music/universal/storage.h',
 'ATtiny88/Music/universal/rational-clocks.h',
 'ATtiny88/Music/universal/gain-table.inc',
 'tools/test-universal-backends.mjs','tools/test-universal-stereo.mjs'];
const report={schema:'micromusic-um88-backend-all-boards',version:1,
 references:{datasheet:'https://ww1.microchip.com/downloads/en/DeviceDoc/doc8008.pdf',
  powerReduction:'8008H section 7.4.3, page 40: restore peripheral clocks before I/O access',
  watchdog:'https://avrdudes.github.io/avr-libc/avr-libc-user-manual/group__avr__watchdog.html',
  watchdogPattern:'naked .init3 before BSS, clear MCUSR before protected watchdog disable',
  registerDefinitions:dfp,registerDefinitionsSha256:sha(fs.readFileSync(absolute(dfp)))},
 sourceTextLfSha256:Object.fromEntries(sources.map(p=>[p,sha(fs.readFileSync(absolute(p),'utf8').replaceAll('\r\n','\n'))])),
 interpolationEndpointPairs:interpolationPairs,startupChecks,smokeChecks,conformance,
 publishedAsmStereoPassed:smokeChecks.filter(x=>x.backend==='avr-asm').every(x=>x.completedSecond),
 cStereoRealtimePassed:smokeChecks.filter(x=>x.backend==='c').every(x=>x.completedSecond),
 hardwareTested:false,note:'Instruction/IRQ model verification; C throughput failures are preserved, not treated as timing qualification.'};
fs.mkdirSync(path.dirname(absolute(reportPath)),{recursive:true});
fs.writeFileSync(absolute(reportPath),JSON.stringify(report,null,2)+'\n');
console.log(reportPath);
