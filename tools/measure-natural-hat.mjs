// Isolate actual AVR percussion, both with its envelope and held for PSD analysis.
import fs from 'node:fs';
import {AVRCore} from '../web-player/lib/avr-core.js';
const out='build/natural-hat';fs.mkdirSync(out,{recursive:true});
for(const name of ['foreground-pwm','natural-hat']){
  const folder=`ATtiny13A/Music/variants/${name}`;
  for(const type of [0,1,2])for(const held of [false,true]){
    const c=new AVRCore(fs.readFileSync(`${folder}/synth.bin`),fs.readFileSync(`${folder}/eeprom.bin`));
    const report=JSON.parse(fs.readFileSync(`${folder}/build-report.json`));
    while(c.pc!==report.labels.idle/2||c.inIRQ)c.step();
    c.r[1]=c.r[19]=c.r[20]=0;c.r[21]=0;c.r[29]=type;c.r[14]=167;c.r[22]=255;c.r[24]=0;c.r[15]=0;c.r[23]=0;c.r[25]=0;
    const pcm=new Float32Array(Math.round(.32*37500));
    for(let i=0;i<pcm.length;i++){
      if(held)c.r[21]=0;
      pcm[i]=(c.nextDuty()-128)/128;
    }
    if(c.lost||c.workLost||c.maxIRQ!==12)throw Error('Percussion timing failure');
    fs.writeFileSync(`${out}/${name}-${type}-${held?'held':'decay'}.f32`,new Uint8Array(pcm.buffer));
  }
}
for(const mode of ['held','decay']){
  const before=fs.readFileSync(`${out}/foreground-pwm-0-${mode}.f32`);
  if(!before.equals(fs.readFileSync(`${out}/natural-hat-0-${mode}.f32`)))throw Error('Bass drum changed');
}
console.log('Isolated real AVR percussion:',out);
