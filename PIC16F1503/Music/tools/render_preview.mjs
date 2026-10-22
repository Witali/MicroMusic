/* Audition the C-port-equivalent 15.625 kHz duty stream, WAV after AC coupling.
 * Audio is produced by the reference synthesis model, not by a compiled PIC binary.
 */
import fs from 'node:fs';import {SoundModel} from '../web/synth-model.mjs';
const seconds=Number(process.argv[2]||14),rate=15625,samples=Math.round(seconds*rate);
const model=new SoundModel();
const wav=Buffer.alloc(44+samples*2);
wav.write('RIFF',0);wav.writeUInt32LE(36+samples*2,4);wav.write('WAVE',8);wav.write('fmt ',12);
wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);
wav.writeUInt32LE(rate,24);wav.writeUInt32LE(rate*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);
wav.write('data',36);wav.writeUInt32LE(samples*2,40);
let prev=0,y=0,mean=0,mi=255,ma=0;const alpha=Math.exp(-2*Math.PI*35/rate);
for(let i=0;i<samples;i++){
  const duty=model.nextSample(),x=(duty-128)/128;
  y=alpha*(y+x-prev);prev=x;const s=Math.max(-32768,Math.min(32767,Math.round(y*23000)));
  wav.writeInt16LE(s,44+i*2);mean+=duty;mi=Math.min(mi,duty);ma=Math.max(ma,duty);
}
fs.writeFileSync(new URL('../reference/preview_pic16_model.wav',import.meta.url),wav);
const stats={generator:'PIC16F1503 C-port reference sound model, not compiled HEX',rate,duration:seconds,meanDuty:mean/samples,minDuty:mi,maxDuty:ma,events:model.eventCount,sections:model.sectionsTraversed,noteoffs:model.noteoffs};
fs.writeFileSync(new URL('../reports/audio-report.json',import.meta.url),JSON.stringify(stats,null,2)+'\n');
console.log(stats);
