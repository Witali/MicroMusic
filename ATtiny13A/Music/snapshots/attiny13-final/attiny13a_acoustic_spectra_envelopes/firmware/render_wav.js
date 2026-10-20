/* Render a listenable 16-bit PCM preview from the executed firmware.
 * The DSP here is strictly an output RC/DC filter and peak normalization,
 * NOT the instrument synthesizer: oscillator samples come from AVRCore.
 */
const fs=require('fs');
const {AVRCore}=require('./avr_core.js');
const sec=Math.max(1,Math.min(60,Number(process.argv[2]||12)));
const sr=37500, count=Math.ceil(sr*sec);
const cpu=AVRCore.fromHex(fs.readFileSync('synth.hex','utf8'));
const samples=new Float64Array(count);
const hipassAlpha=Math.exp(-2*Math.PI*28/sr), lowpassAlpha=1-Math.exp(-2*Math.PI*9000/sr);
let px=0,py=0,lp1=0,lp2=0,peak=0;
for(let i=0;i<count;i++){
  const x=(cpu.nextDuty()-127.5)/127.5;
  py=hipassAlpha*(py+x-px);px=x;
  lp1+=lowpassAlpha*(py-lp1);
  lp2+=lowpassAlpha*(lp1-lp2);
  samples[i]=lp2;peak=Math.max(peak,Math.abs(lp2));
}
let pcm=Buffer.alloc(count*2),scale=peak>0?0.85/peak:0;
for(let i=0;i<count;i++)pcm.writeInt16LE(Math.max(-32767,Math.min(32767,Math.round(samples[i]*scale*32767))),i*2);
const buf=Buffer.alloc(44+pcm.length);
buf.write('RIFF',0);buf.writeUInt32LE(36+pcm.length,4);buf.write('WAVEfmt ',8);
buf.writeUInt32LE(16,16);buf.writeUInt16LE(1,20);buf.writeUInt16LE(1,22);
buf.writeUInt32LE(sr,24);buf.writeUInt32LE(sr*2,28);buf.writeUInt16LE(2,32);buf.writeUInt16LE(16,34);
buf.write('data',36);buf.writeUInt32LE(pcm.length,40);pcm.copy(buf,44);
fs.writeFileSync('preview.wav',buf);
console.log(`WAV ${sec}s @ ${sr}Hz, ${buf.length} bytes; executed ${cpu.irqCount} PWM IRQs, worst ISR ${cpu.maxIRQ} cycles, overruns ${cpu.lost}; peak ${JSON.stringify(cpu.peakInfo)}`);
