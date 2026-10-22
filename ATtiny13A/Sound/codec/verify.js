/* Cycle-counting emulator check, no audio dependencies. */
const {AVRCore}=require('./avr_emulator.js');
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const manifest=JSON.parse(fs.readFileSync(__dirname+'/manifest.json','utf8'));
let ok=true;
for(const [name,v] of Object.entries(manifest)){
 const dir=path.join(__dirname,'examples',name);
 const firmware=fs.readFileSync(path.join(dir,'firmware.bin'));
 const reference=fs.readFileSync(path.join(dir,'avr_pcm.raw'));
 const av=new AVRCore(firmware);
 let differences=0;let prev=0;let stalled=0;let worstGap=0;
 for(let i=0;i<reference.length;i++){
  const sample=av.takeSample();
  if(sample!==reference[i])differences++;
  const gap=av.cycles-prev;
  if(i>0 && gap>1290)stalled++;
  if(i>0)worstGap=Math.max(worstGap,gap);
  prev=av.cycles;
 }
 const sha=crypto.createHash('sha256').update(reference).digest('hex');
 const valid=firmware.length<=1024 && differences===0 && stalled===0 && av.missedOverflows===0 && sha===v.pcm_sha256;
 console.log(`${name}: ${valid?'OK':'FAIL'}; flash=${firmware.length}; samples=${reference.length}; mismatches=${differences}; missed IRQ=${av.missedOverflows}; stalled=${stalled}; max ISR=${av.maxISR}; max gap=${worstGap}`);
 ok &&=valid;
}
if(!ok)process.exitCode=1;
