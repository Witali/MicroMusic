// Qualification only: never execute firmware or rewrite raw audit reports.
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const sha=value=>createHash('sha256').update(value).digest('hex');
const json=file=>JSON.parse(fs.readFileSync(file));

export function clippingBaseline(job,revision='8a0da608'){
 const file=`ATtiny88/Music/universal/${job.base}/${job.name}/verification.json`;
 const result=spawnSync('git',['show',revision+':'+file],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);
 const report=JSON.parse(result.stdout);
 assert.equal(report.cpuHz,job.cpuHz);assert.equal(report.scoreSha256,job.scoreSha256,'Baseline score must match the IRQ-only release');
 assert.equal(report.passed,true);assert.equal(report.fifoUnderruns,0);assert.equal(report.lostInterrupts,0);
 assert.ok(Number.isInteger(report.clippedChannelSamples)&&report.clippedChannelSamples>=0);
 return {revision,file,reportSha256:sha(result.stdout),flashSha256:report.flashSha256,
  clippedChannelSamples:report.clippedChannelSamples};
}

export function qualifyIRQReport(job,report,exitCode=0){
 try{
  assert.equal(exitCode,0);assert.equal(report.passed,true);assert.ok(report.completeLoops>=1);
  assert.equal(report.flashSha256,job.flashSha256);assert.equal(report.engineSha256,job.engineSha256);
  assert.equal(report.scoreSha256,job.scoreSha256);
  assert.equal(report.fifoUnderruns,0);assert.equal(report.lostInterrupts,0);
  assert.equal(report.fifoCapacityFrames,192/job.channels,'Final release uses a 192-byte ring');
  assert.equal(report.maxISRCycles,job.channels===1?34:38,'Final normal IRQ cycle count');
  assert.equal(report.clippedChannelSamples,job.clippingBaseline.clippedChannelSamples,'Clipping must equal the unchanged score baseline');
  assert.ok(report.minimumQueuedFrames>0);assert.ok(report.stackMarginBytes>=0);
  assert.ok(report.checkedGeneratedFrames>0&&report.checkedIRQOutputs>0);
  assert.deepEqual(report.generatedPwmActual,report.generatedPwmReference);
  assert.deepEqual(report.consumedPwmActual,report.consumedPwmReference);
  assert.equal(report.generatedPwmActual.bytes,report.checkedGeneratedFrames*job.channels);
  assert.equal(report.consumedPwmActual.bytes,report.checkedIRQOutputs*job.channels);
  if(job.channels===1){
   assert.equal(report.strictMonoOCR1ANoWrites,true);assert.equal(report.monoOCR1AWriteAttempts,0);
   assert.ok(report.monoObservableBoundaries>0);
   assert.equal(report.monoPB1AndCOM1AInactive,true,'Mono keeps the unused pin and compare output inactive');
  }
  return {passed:true};
 }catch(error){return {passed:false,failure:error.message};}
}

export function requalifyIRQRelease(output=path.resolve('build/irq-release-audits'),revision='8a0da608'){
 const summaryFile=path.join(output,'summary.json'),prepared=json(path.join(output,'prepared.json'));
 const summary=json(summaryFile);assert.equal(summary.jobs.length,18,'Wait for every expensive audit to finish');
 assert.equal(summary.cancelled,false,'Cannot qualify a cancelled run');
 const originalFile=path.join(output,'summary-before-clipping-requalification.json');
 if(!fs.existsSync(originalFile))fs.copyFileSync(summaryFile,originalFile);
 const originalSha=sha(fs.readFileSync(originalFile)),rawHashes=[];
 const jobs=summary.jobs.map(row=>{
  const saved=prepared.baseline.find(s=>s.cpuHz===row.cpuHz&&s.name===row.name);assert.ok(saved);
  const folder=path.join(output,'images',String(row.cpuHz),row.name),meta=json(path.join(folder,'build-report.json'));
  const score=json(path.join(folder,'score.json')),file=path.join(folder,'verification.json');
  const report=json(file);rawHashes.push({file,sha256:sha(fs.readFileSync(file))});
  assert.equal(meta.pwmBufferBytes,192,'Final release ring byte capacity');
  assert.equal(sha(fs.readFileSync(path.join(folder,'synth.bin'))),meta.flashSha256);
  assert.equal(sha(JSON.stringify(score)),saved.scoreSha256);
  const job={...saved,flashSha256:meta.flashSha256,engineSha256:meta.engineSha256};
  job.clippingBaseline=clippingBaseline(job,revision);
  const qualified=qualifyIRQReport(job,report,row.exitCode);
  const result={...row,...qualified,baselineClippedChannelSamples:job.clippingBaseline.clippedChannelSamples,
   clippedChannelSamples:report.clippedChannelSamples,clippingBaseline:job.clippingBaseline};
  if(qualified.passed)delete result.failure;
  return result;
 });
 for(const raw of rawHashes)assert.equal(sha(fs.readFileSync(raw.file)),raw.sha256,'Raw audit reports remain unchanged');
 const corrected={...summary,jobs,passed:jobs.every(row=>row.passed),qualificationCorrection:{
  reason:'Original live aggregate incorrectly required zero clipping; qualify against unchanged score-specific clipping instead.',
  baselineRevision:revision,originalSummarySha256:originalSha,originalSummary:'summary-before-clipping-requalification.json',
  qualificationSourceTextLfSha256:sha(fs.readFileSync(fileURLToPath(import.meta.url),'utf8').replace(/\r\n/g,'\n')),
  rawReportsUnchanged:true,rawReportHashes:rawHashes.map(row=>({file:path.relative(output,row.file).replaceAll('\\','/'),sha256:row.sha256}))}};
 fs.writeFileSync(summaryFile,JSON.stringify(corrected,null,2)+'\n');
 console.log(JSON.stringify({qualified:jobs.length,passed:corrected.passed,baselineRevision:revision,rawReportsUnchanged:true}));
 return corrected;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const output=process.argv.find(a=>a.startsWith('--directory='))?.slice(12)||path.resolve('build/irq-release-audits');
 const revision=process.argv.find(a=>a.startsWith('--baseline='))?.slice(11)||'8a0da608';
 process.exitCode=requalifyIRQRelease(output,revision).passed?0:1;
}
