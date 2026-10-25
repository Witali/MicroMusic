import {test}from 'node:test';
import assert from 'node:assert/strict';
import {qualifyIRQReport}from './qualify-universal-irq-release.mjs';
const job={channels:1,flashSha256:'flash',engineSha256:'engine',scoreSha256:'score',clippingBaseline:{clippedChannelSamples:32}};
const report={passed:true,completeLoops:1,flashSha256:'flash',engineSha256:'engine',scoreSha256:'score',
 fifoUnderruns:0,lostInterrupts:0,fifoCapacityFrames:192,maxISRCycles:34,
 clippedChannelSamples:32,minimumQueuedFrames:1,stackMarginBytes:0,
 checkedGeneratedFrames:4,checkedIRQOutputs:1,generatedPwmActual:{sha256:'generated',bytes:4},
 generatedPwmReference:{sha256:'generated',bytes:4},consumedPwmActual:{sha256:'irq',bytes:1},
 consumedPwmReference:{sha256:'irq',bytes:1},strictMonoOCR1ANoWrites:true,monoOCR1AWriteAttempts:0,
 monoObservableBoundaries:1,monoPB1AndCOM1AInactive:true};
test('IRQ qualification preserves the exact clipping baseline and does not normalize it away',()=>{
 assert.equal(qualifyIRQReport(job,report).passed,true);
 for(const count of [0,31,33])assert.equal(qualifyIRQReport(job,{...report,clippedChannelSamples:count}).passed,false);
 assert.equal(qualifyIRQReport({...job,clippingBaseline:{clippedChannelSamples:0}},report).passed,false);
 assert.equal(qualifyIRQReport({...job,clippingBaseline:{clippedChannelSamples:0}},{...report,clippedChannelSamples:0}).passed,true);
});
test('IRQ qualification keeps image, stream, timing and strict mono checks mandatory',()=>{
 for(const changed of [{flashSha256:'wrong'},{fifoUnderruns:1},{lostInterrupts:1},
  {generatedPwmActual:{sha256:'wrong',bytes:4}},{monoOCR1AWriteAttempts:1},{strictMonoOCR1ANoWrites:false}]){
  assert.equal(qualifyIRQReport(job,{...report,...changed}).passed,false);
 }
});
test('IRQ qualification requires final cycle counts, release ring and inactive mono pin',()=>{
 for(const changed of [{maxISRCycles:35},{fifoCapacityFrames:96},{monoPB1AndCOM1AInactive:false}]){
  assert.equal(qualifyIRQReport(job,{...report,...changed}).passed,false);
 }
});
