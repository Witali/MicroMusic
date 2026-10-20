/* Play six isolated instrument notes via the actual AVR machine-code interpreter.
 * This file changes only simulated chip registers between demonstrations.
 * All harmonic generation still executes in synth.hex (no JS oscillator).
 */
const fs = require('fs');
const {AVRCore} = require('./avr_core.js');
const sr=37500;
const cpu=AVRCore.fromHex(fs.readFileSync('synth.hex','utf8'));
// Wait until reset code, timer setup and first ISR are complete.
cpu.nextDuty();
const tests=[
  ['Piano C3 (low)', 'piano',48], ['Piano D4 (mid)','piano',62],
  ['Piano A5 (high)','piano',81], ['Guitar G2 (low)','guitar',43],
  ['Guitar D4 (mid)','guitar',62], ['Guitar A4 (high)','guitar',69],
  ['Violin G3 (low)', 'violin',55], ['Violin D4 (mid)','violin',62],
  ['Violin A4 (high)','violin',69], ['Violin D5 (top)','violin',74],
];
const length=Math.round(0.65*sr),silence=Math.round(0.15*sr);
const out=new Float64Array((length+silence)*tests.length);
let pos=0, peak=0, previousInput=0, highPass=0, lowPass=0;
const hp=Math.exp(-2*Math.PI*25/sr), lp=1-Math.exp(-2*Math.PI*9000/sr);
function step(mute) {
  // Keep the composition's notes and rhythm from disrupting the solo test.
  cpu.r[25]=0;cpu.r[21]=4;cpu.r[22]=255;
  if(mute){cpu.r[19]=4;cpu.r[20]=4}
  const duty=cpu.nextDuty();
  const x=(duty-127.5)/127.5;
  highPass=hp*(highPass+x-previousInput);previousInput=x;
  lowPass+=lp*(highPass-lowPass);
  out[pos++]=lowPass;peak=Math.max(peak,Math.abs(lowPass));
}
for(const [label,inst,note] of tests){
  let step16=Math.round(440*2**((note-69)/12)*65536/sr);
  // Silence the untouched violin (its wave remains DC-only).
  cpu.r[4]=0;cpu.r[5]=0;cpu.r[1]=0;
  cpu.r[6]=0;cpu.r[7]=0;cpu.r[10]=0;cpu.r[11]=0;
  // Align decay clock to attack so register comparisons are fair.
  cpu.r[24]=0;cpu.r[15]=0;cpu.r[23]=0;
  if(inst==='violin'){
    cpu.r[4]=step16&255;cpu.r[5]=step16>>8;cpu.r[1]=3;
    cpu.r[8]=0;cpu.r[9]=0;cpu.r[19]=4;cpu.r[12]=0;cpu.r[13]=0;cpu.r[20]=4;
  } else if(inst==='piano'){
    cpu.r[8]=step16&255;cpu.r[9]=step16>>8;cpu.r[19]=0;
    cpu.r[12]=0;cpu.r[13]=0;cpu.r[20]=4;
  } else {
    cpu.r[8]=0;cpu.r[9]=0;cpu.r[19]=4;
    cpu.r[12]=step16&255;cpu.r[13]=step16>>8;cpu.r[20]=0;
  }
  console.log(label, 'step',step16,'stepHi',step16>>8, 'samples',length);
  for(let n=0;n<length;n++)step(false);
  for(let n=0;n<silence;n++)step(true);
}
const pcm=Buffer.alloc(out.length*2),scale=peak>0?0.86/peak:0;
for(let i=0;i<out.length;i++)pcm.writeInt16LE(Math.max(-32768,Math.min(32767,Math.round(32767*scale*out[i]))),i*2);
const wav=Buffer.alloc(44+pcm.length);
wav.write('RIFF',0);wav.writeUInt32LE(36+pcm.length,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(sr,24);wav.writeUInt32LE(sr*2,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(pcm.length,40);pcm.copy(wav,44);
fs.writeFileSync('register_demo.wav',wav);
fs.writeFileSync('register_demo.json', JSON.stringify({sampleRate:sr,noteSeconds:length/sr,gapSeconds:silence/sr,tests:tests.map(([label,instrument,midi])=>({label,instrument,midi}))},null,2));
console.log('WAV',out.length/sr,'s; CPU IRQ',cpu.irqCount,'max',cpu.maxIRQ,'lost',cpu.lost);
