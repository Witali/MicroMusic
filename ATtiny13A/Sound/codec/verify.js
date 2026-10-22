/* Full cycle-counting AVR verification of NEW-ONLY firmware. */
const {AVRCore}=require('./avr_emulator.js');
const fs=require('fs'),path=require('path');
const root=__dirname, voices=['chego','otvechaesh','vinni'];
const summary={};
let failed=false;
for(const voice of voices){
 const dir=path.join(root,'samples',voice);
 const program=fs.readFileSync(path.join(dir,'firmware.bin'));
 const expected=fs.readFileSync(path.join(dir,'expected_pcm.raw'));
 const expectedFull=fs.readFileSync(path.join(dir,'reference_pcm.raw'));
 const core=new AVRCore(program);
 let mismatches=0, missedSamples=0, lastCycle=0, maxGap=0;
 const pcm=Buffer.alloc(expected.length);
 for(let i=0;i<expected.length;i++){
   const x=core.takeSample();pcm[i]=x;
   if(x!==expected[i])mismatches++;
   const gap=core.cycles-lastCycle;
   if(i && gap>1290)missedSamples++;
   if(i)maxGap=Math.max(maxGap,gap);
   lastCycle=core.cycles;
 }
 fs.writeFileSync(path.join(dir,'avr_pcm.raw'),pcm);
 const info={bytes:program.length,decoderBytes:program.length-fs.statSync(path.join(dir,'speech.vbr')).size-1,
  savingsVsFixedImage: (364+fs.statSync(path.join(dir,'speech_full.bin')).size+1)-program.length,
  samples:expected.length,pcmDiff:mismatches,missedOverflows:core.missedOverflows,
  lateAudioSamples:missedSamples,maxISR:core.maxISR,maxGap};
 summary[voice]=info;
 console.log(voice,JSON.stringify(info));
 if(mismatches||core.missedOverflows||missedSamples||program.length>1024)failed=true;
}
fs.writeFileSync(path.join(root,'verification.json'),JSON.stringify(summary,null,2));
if(failed)process.exit(1);
