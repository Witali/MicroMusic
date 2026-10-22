const fs=require('fs'),path=require('path');
const {AVRCore}=require('./avr_emulator.js');
const root=__dirname;const report={};let failed=false;
for(let name of ['chego','otvechaesh','vinni']){
  const d=path.join(root,'samples',name);
  const p=fs.readFileSync(path.join(d,'firmware.bin'));
  const expected=fs.readFileSync(path.join(d,'expected_pcm.raw'));
  const cpu=new AVRCore(p);const actual=Buffer.alloc(expected.length);
  let mismatch=0,late=0,last=0;
  for(let j=0;j<expected.length;j++){
    const v=cpu.takeSample();actual[j]=v;
    if(v!==expected[j])mismatch++;
    if(j>0 && cpu.cycles-last>1300)late++;
    last=cpu.cycles;
  }
  fs.writeFileSync(path.join(d,'avr_pcm.raw'),actual);
  report[name]={flash:p.length,samples:expected.length,differences:mismatch,missedTimer:cpu.missedOverflows,lateAudio:late,maxISR:cpu.maxISR};
  if(mismatch||cpu.missedOverflows||late||p.length>1024)failed=true;
  console.log(name,report[name]);
}
fs.writeFileSync(path.join(root,'verification.json'),JSON.stringify(report,null,2));
if(failed)process.exit(1);
