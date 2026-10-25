// Audit a frozen GPIOR release in isolated copies; retained firmware remains read-only.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawn,spawnSync} from 'node:child_process';
import {clippingBaseline,qualifyIRQReport} from './qualify-universal-irq-release.mjs';
const root=process.cwd(),output=path.join(root,'build/irq-release-audits');
const json=p=>JSON.parse(fs.readFileSync(p));
const sha=b=>createHash('sha256').update(b).digest('hex');
const prepared=json(path.join(output,'prepared.json'));
const workers=Number(process.argv.find(a=>a.startsWith('--jobs='))?.slice(7)||6);
assert.ok(Number.isInteger(workers)&&workers>=1&&workers<=8);
const expectedSizes=(process.argv.find(a=>a.startsWith('--expected-core-bytes='))?.split('=')[1]||'2130,2234,2182,2286').split(',').map(Number);
assert.equal(expectedSizes.length,4);assert.ok(expectedSizes.every(n=>Number.isInteger(n)&&n>0));
assert.equal(sha(fs.readFileSync(path.join(output,'audit-with-write-trace.mjs'))),prepared.instrumentedAuditSha256);
const observedCheckoutRevision=spawnSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).stdout.trim();
const jobs=[];
for(const saved of prepared.baseline){
 const source=path.join(root,'ATtiny88/Music/universal',saved.base,saved.name);
 const meta=json(path.join(source,'build-report.json')),score=json(path.join(source,'score.json'));
 assert.equal(meta.cpuHz,saved.cpuHz);assert.equal(meta.backend,'avr-asm');
 assert.equal(meta.irqScratch,'gpior','Final release must explicitly select GPIOR scratch');
 assert.equal(meta.irqScratchSelection,'gpior');
 assert.deepEqual(meta.reservedIORegisters,['GPIOR0','GPIOR1','GPIOR2']);
 assert.equal(meta.configuredChannels,saved.channels);assert.equal(score.controlTicks,saved.controlTicks);
 assert.equal(meta.pwmBufferBytes,192,'Final release ring byte capacity');
 assert.equal(meta.engineBytes,expectedSizes[(saved.cpuHz===16000000?2:0)+(saved.channels-1)],'Frozen release core size');
 assert.equal(sha(JSON.stringify(score)),saved.scoreSha256,'No score/note changes during IRQ optimization');
 assert.equal(sha(fs.readFileSync(path.join(source,'synth.bin'))),meta.flashSha256);
 for(const [file,expected]of Object.entries(meta.sourceInputs)){
  assert.equal(sha(fs.readFileSync(path.join(root,file),'utf8').replace(/\r\n/g,'\n')),expected,'Current frozen input '+file);
 }
 const directory=path.join(output,'images',String(saved.cpuHz)),target=path.join(directory,saved.name);
 fs.mkdirSync(target,{recursive:true});
 for(const file of ['score.json','build-report.json','synth.bin'])fs.copyFileSync(path.join(source,file),path.join(target,file));
 jobs.push({...saved,directory,clippingBaseline:clippingBaseline(saved),weight:meta.cpuHz*meta.controlTicks*(meta.voices+4),flashSha256:meta.flashSha256,
  engineSha256:meta.engineSha256,sourceInputs:meta.sourceInputs});
}
assert.equal(jobs.length,18);
const sourceTextLfSha256=jobs[0].sourceInputs;
for(const job of jobs)assert.deepEqual(job.sourceInputs,sourceTextLfSha256,'All release images bind the same frozen source text');
jobs.sort((a,b)=>b.weight-a.weight);
let next=0;const results=[],started=Date.now();
let stopRequested=false;const children=new Set();
const requestStop=()=>{
 if(stopRequested)return;
 stopRequested=true;
 console.log('Stopping this audit run and its own children; staged inputs are retained.');
 for(const child of children)child.kill();
};
process.on('SIGINT',requestStop);process.on('SIGTERM',requestStop);
const stopFile=path.join(output,'stop.request');
assert.ok(!fs.existsSync(stopFile),'Remove or archive the old stop request before beginning a new run');
const stopWatcher=setInterval(()=>{if(fs.existsSync(stopFile))requestStop();},250);
stopWatcher.unref();
async function worker(){
 while(!stopRequested&&next<jobs.length){
  const job=jobs[next++],log=path.join(output,job.base+'-'+job.name+'.log');
  const result=await new Promise(resolve=>{
   const child=spawn(process.execPath,[path.join(output,'audit-with-write-trace.mjs'),'--directory='+job.directory,job.name],{cwd:root,windowsHide:true});
   children.add(child);
   let text='';child.stdout.on('data',b=>text+=b);child.stderr.on('data',b=>text+=b);
   child.on('error',error=>{children.delete(child);text+=error.stack;resolve({exitCode:-1,text});});
   child.on('close',code=>{children.delete(child);resolve({exitCode:code,text});});
  });
  fs.writeFileSync(log,result.text);
  const file=path.join(job.directory,job.name,'verification.json');
  const report=fs.existsSync(file)?json(file):{};
  const qualified=qualifyIRQReport(job,report,result.exitCode),passed=qualified.passed;
  const row={name:job.name,cpuHz:job.cpuHz,channels:job.channels,exitCode:result.exitCode,passed,
   minimumFIFO:report.minimumQueuedFrames,stackMargin:report.stackMarginBytes,maxISRCycles:report.maxISRCycles,
   checkedIRQOutputs:report.checkedIRQOutputs,rawPwmStreamsEqual:report.rawPwmStreamsEqual,
   strictMonoOCR1ANoWrites:report.strictMonoOCR1ANoWrites,wallSeconds:report.wallSeconds,
   baselineClippedChannelSamples:job.clippingBaseline.clippedChannelSamples,clippedChannelSamples:report.clippedChannelSamples,
   clippingBaseline:job.clippingBaseline,
   reportFile:path.relative(root,file).replaceAll('\\','/'),
   ...(!passed?{failure:qualified.failure||report.failure||result.text.slice(-2000)}:{})};
  results.push(row);console.log(JSON.stringify(row));
  fs.writeFileSync(path.join(output,'progress.json'),JSON.stringify({finished:results.length,total:jobs.length,jobs:results},null,2)+'\n');
 }
}
console.log('Starting '+jobs.length+' full-loop GPIOR audio audits with '+workers+' workers; retained inputs are read-only.');
await Promise.all(Array.from({length:workers},worker));
clearInterval(stopWatcher);
const passed=results.length===18&&results.every(r=>r.passed);
fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify({observedCheckoutRevision,sourceTextLfSha256,
 method:'Complete loop and restart against independent JSON arithmetic; every generated and consumed PWM byte checked and hashed; mono decoded write tracing across all execution with SRAM-only bulk acceleration.',
 modelsOnly:true,electricalPwmEdgesMeasured:false,irqScratch:'gpior',preparedSource:prepared,
 jobs:results,passed,cancelled:stopRequested,elapsedSeconds:(Date.now()-started)/1000},null,2)+'\n');
process.exitCode=stopRequested?130:passed?0:1;
