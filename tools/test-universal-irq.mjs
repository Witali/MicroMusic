// Execute actual isolated C/ASM IRQ functions; no musical/control model is involved.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {AVRCore} from '../web-player/lib/avr-reference.js';
const root=fileURLToPath(new URL('../',import.meta.url));
const option=(name,fallback)=>process.argv.find(arg=>arg.startsWith('--'+name+'='))?.slice(name.length+3)||fallback;
const manifestPath=path.resolve(root,option('manifest','build/universal/irq-driver/manifest.json'));
const reportPath=path.resolve(root,option('report','build/universal/irq-driver/verification.json'));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const manifest=JSON.parse(fs.readFileSync(manifestPath));
for(const [file,hash] of Object.entries(manifest.sourceTextLfSha256))
 assert.equal(sha(fs.readFileSync(path.resolve(root,file),'utf8').replaceAll('\r\n','\n')),hash,'Rebuild IRQ fixtures after changing '+file);
const dfp='ATtiny88/Music/universal/vendor/ATtiny_DFP/3.4.278/atdf/ATtiny88.atdf';
const registers=new Map([...fs.readFileSync(path.resolve(root,dfp),'utf8').matchAll(/<register\b([^>]+)>/g)].map(match=>{
 const attributes=Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(x=>[x[1],x[2]]));
 return [attributes.name,Number(attributes.offset)];
}));
const gpNames=['GPIOR0','GPIOR1','GPIOR2'],gp=gpNames.map(name=>{assert.ok(registers.has(name));return registers.get(name);});
function check(meta,binary){
 const core=new AVRCore(binary,null,{target:'attiny88',cpuHz:meta.cpuHz,fastBlocks:false});
 const at=name=>{assert.ok(Number.isInteger(meta.labels[name]),name);return meta.labels[name]-0x800000;};
 const size=meta.pwmBufferBytes,channels=meta.configuredChannels,gpior=meta.irqScratch==='gpior';
 assert.equal(at('um_ring')&255,0,'FIFO page alignment');
 assert.equal(sha(binary),meta.irqSha256);assert.equal(binary.length,meta.irqBytes);
 const summary={irqScratch:meta.irqScratch,capacity:size,channels,irqBytes:meta.irqBytes,irqSha256:sha(binary),cases:0,
  nonemptyCycles:[],emptyCycles:[],nonemptyStackBytes:[],emptyStackBytes:[]};
 let accesses=[];
 const originalRead=core.readData.bind(core),originalWrite=core.writeIO.bind(core);
 core.readData=address=>{accesses.push(['read',address]);return originalRead(address);};
 core.writeIO=(io,value)=>{accesses.push(['write',io+32]);return originalWrite(io,value);};
 for(let read=0;read<size;read+=channels)for(const empty of [false,true]){
  const boundary=read===0||read===size-channels;
  const flagsToTest=boundary?Array.from({length:128},(_,i)=>i):[(read*29+41)&127];
  for(const flags of flagsToTest)for(let pattern=0;pattern<(boundary?2:1);pattern++){
   const counter=boundary?flags*2+pattern:255;
   core.data[at('um_read')]=read;core.data[at('um_write')]=empty?read:(read+channels)%size;
   core.data[at('um_underruns')]=counter;
   const left=(read*73+flags+pattern*128)&255,right=(left+37)&255;
   core.data[at('um_ring')+read]=left;if(channels===2)core.data[at('um_ring')+read+1]=right;
   core.data[core.profile.timer.ocra]=91;core.data[core.profile.timer.ocra+1]=0x5a;
   core.data[core.profile.timer.ocrb]=83;core.data[core.profile.timer.ocrb+1]=0x69;
   gp.forEach((address,i)=>core.data[address]=(flags*17+i*79+read+pattern*128)&255);
   const savedGP=gp.map(address=>core.data[address]);
   for(let r=0;r<32;r++)core.r[r]=(r*17+read+flags*3+pattern*128)&255;
   const saved=[...core.r];core.sreg=flags;core.sp=767;core.minSP=767;core.pushPC(0);
   core.pc=meta.labels['__vector_'+core.profile.timer.vector]/2;accesses=[];
   const start=core.cyc;let steps=0;
   do{core.step();assert.ok(steps++<128,'Bounded interrupt');}while(core.pc!==0);
   assert.deepEqual([...core.r],saved,'Every interrupted register, including all r1 values');
   assert.equal(core.sreg,flags|128,'All interrupted SREG flags; RETI sets I');assert.equal(core.sp,767);
   assert.equal(core.data[at('um_read')],empty?read:(read+channels)%size);
   assert.equal(core.data[at('um_underruns')],empty?(counter+1)&255:counter,'Exact counter update and overflow');
   const word=address=>core.data[address]|core.data[address+1]<<8;
   assert.equal(word(core.profile.timer.ocra),empty||channels===1?0x5a5b:left);
   assert.equal(word(core.profile.timer.ocrb),empty?0x6953:channels===1?left:right);
   if(channels===1)assert.ok(!accesses.some(([,address])=>address===core.profile.timer.ocra||address===core.profile.timer.ocra+1),
    'Mono never reads or writes either OCR1A byte');
   if(gpior)assert.deepEqual(gp.map(address=>core.data[address]),[saved[16],saved[26],saved[27]],'All three explicit GPIOR reservations');
   else {
    assert.deepEqual(gp.map(address=>core.data[address]),savedGP,'Stack and compiler ISR preserve inherited GPIOR contents');
    assert.ok(!accesses.some(([,address])=>gp.includes(address)),'Stack and compiler ISR never access GPIOR');
   }
   const key=empty?'empty':'nonempty';summary[key+'Cycles'].push(core.cyc-start+6);
   summary[key+'StackBytes'].push(767-core.minSP);summary.cases++;
  }
 }
 for(const key of ['nonemptyCycles','emptyCycles','nonemptyStackBytes','emptyStackBytes'])
  summary[key]=[...new Set(summary[key])].sort((a,b)=>a-b);
 return summary;
}
const results=manifest.fixtures.map(fixture=>{
 const meta=JSON.parse(fs.readFileSync(fixture.metadata)),binary=fs.readFileSync(fixture.binary);
 try{return check(meta,binary);}catch(error){console.error(fixture.metadata);throw error;}
});
const report={schema:'micromusic-um88-irq-verification',version:1,passed:true,hardwareTested:false,
 instructionEngine:'shared JavaScript AVR reference',cpu:manifest.cpu,toolchainVersion:manifest.toolchainVersion,
 sourceTextLfSha256:manifest.sourceTextLfSha256,registerDefinitions:dfp,registerDefinitionsSha256:sha(fs.readFileSync(path.resolve(root,dfp))),
 entryAndVectorCycles:6,configurations:results.length,cases:results.reduce((sum,result)=>sum+result.cases,0),
 capacities:{minimum:8,maximum:192,step:4},channels:[1,2],
 allInterruptedRegistersAndSregPreserved:true,all256RegisterValuesCovered:true,all128SavedSregValuesCovered:true,
 allUnderrunCounterValuesCovered:true,monoOcrANeverAccessed:true,emptyAndWrapExact:true,
 gpiorReservation:gpNames.map((name,i)=>({register:name,interruptedCpuRegister:[16,26,27][i]})),
 gpiorConstraint:'Exclusive driver ownership; PWM interrupt must remain non-nested',
 compilerAndStackPreserveGpior:true,results};
fs.mkdirSync(path.dirname(reportPath),{recursive:true});fs.writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');
console.log(`${results.length} IRQ configurations, ${report.cases} cases: exact C/ASM output, registers, SREG, counters, wrap and GPIOR ownership`);
console.log(reportPath);
