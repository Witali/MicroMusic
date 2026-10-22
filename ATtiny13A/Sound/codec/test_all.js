const {AVRCore}=require('./mini_emulator.js');const fs=require('fs');const path=require('path');
const folders=[];const base=__dirname;
for (let s of ['chego','otvechaesh','vinni']) for(let v of ['nano','full','soft']) folders.push(path.join(base,'mini_build',s,v));
for (let s of ['chego','otvechaesh','vinni']) for(let v of ['keyframe','adaptive']) folders.push(path.join(base,'new_matrix',s,v));
let report=[];
for(const d of folders){
 const frames=(d.includes('/vinni/')?87:d.includes('/otvechaesh/')?31:36);
 const core=AVRCore.fromHex(fs.readFileSync(d+'/tinylpc.hex','utf8'));
 const out=Buffer.alloc(frames*256);let prev=0,max=0,gaps=[],min=256,maxp=0;
 let error=null;
 try {
 for(let j=0;j<out.length;j++){
  out[j]=core.takeSample();min=Math.min(min,out[j]);maxp=Math.max(maxp,out[j]);
  if(j){const g=core.cycles-prev;max=Math.max(max,g);if(g>1290){gaps.push([j,g])}}
  prev=core.cycles;
 }
 } catch(e){error=e.message}
 const record={clip:d.split('/').slice(-2,-1)[0],codec:d.split('/').slice(-1)[0],flash:fs.statSync(d+'/tinylpc.bin').size,bytes:fs.statSync(d+'/voice_tinylpc.bin').size,irq:core.irqCount,missed:core.missedOverflows,maxISR:core.maxISR,underruns:gaps.length,firstGaps:gaps.slice(0,10),maxGap:max,min,maxp,error};
 fs.writeFileSync(d+'/avr_pcm.raw',out);
 report.push(record);console.log(JSON.stringify(record));
}
fs.writeFileSync(base+'/verification.json',JSON.stringify(report,null,2));
