// Render the actual AVR image through the player's default filters at 48 kHz.
// Use the same non-resonant Q=0.5 as the player's cascaded RC approximation.
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import { Renderer } from '../web-player/lib/renderer.js';
import {parseHex} from '../web-player/lib/hex.js';
const args=process.argv.slice(2),normalize=args.includes('--normalize'),positional=args.filter(x=>x!=='--normalize');
const folder = positional[0], seconds = Number(positional[1] || 14);
const cutoff=Number(positional[2]||9000),q=Number(positional[3]||.5);
if (!folder || !Number.isFinite(seconds) || seconds <= 0 || seconds > 300)
  throw new Error('Usage: node tools/render-firmware-preview.mjs firmware-folder [seconds] [cutoff] [Q] [--normalize]');
const channels=JSON.parse(fs.readFileSync(path.join(folder,'build-report.json'))).audioChannels||1;
const rate = 48000, renderer = new Renderer({pwmHz: 37500,audioChannels:channels,
  flashHex: fs.readFileSync(path.join(folder, 'synth.hex'), 'utf8'),
  eepromHex: fs.readFileSync(path.join(folder, 'eeprom.hex'), 'utf8')}, rate,{filtered:false});
function biquad(type, frequency) {
  const w = 2 * Math.PI * frequency / rate, cos = Math.cos(w), alpha = Math.sin(w) / (2 * q);
  const a0 = 1 + alpha, b0 = (type === 'highpass' ? 1 + cos : 1 - cos) / 2;
  const b1 = type === 'highpass' ? -(1 + cos) : 1 - cos;
  const a1 = -2 * cos / a0, a2 = (1 - alpha) / a0;
  let z1 = 0, z2 = 0;
  return x => { const y = b0 / a0 * x + z1; z1 = b1 / a0 * x - a1 * y + z2; z2 = b0 / a0 * x - a2 * y; return y; };
}
const filters=Array.from({length:channels},()=>({high:biquad('highpass',35),low:biquad('lowpass',cutoff)}));
const count = Math.round(seconds * rate), pcm = Buffer.alloc(count * 2 * channels);
const samples=normalize?new Float64Array(count*channels):null;
let min = 0, max = 0;
for (let start = 0; start < count; start += 4096) {
  const block = renderer.render(Math.min(4096, count - start));
  for (let j = 0; j < block.length; j++) {
    const {high,low}=filters[j%channels];
    const y = low(high(block[j])) * .65; min = Math.min(min, y); max = Math.max(max, y);
    if(normalize)samples[start*channels+j]=y;
    else{
      if (Math.abs(y) >= 1) throw new Error('Preview clipped');
      pcm.writeInt16LE(Math.round(y * 32767), (start * channels + j) * 2);
    }
  }
}
const inputPeak=Math.max(-min,max),gain=normalize&&inputPeak>0?1/inputPeak:1;
if(normalize)for(let i=0;i<samples.length;i++){
  const value=Math.round(samples[i]*gain*32767);
  if(value < -32767||value>32767)throw Error('Normalized preview clipped');
  pcm.writeInt16LE(value,i*2);
}
const header = Buffer.alloc(44); header.write('RIFF'); header.writeUInt32LE(36 + pcm.length, 4); header.write('WAVEfmt ', 8);
header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(channels, 22); header.writeUInt32LE(rate, 24);
header.writeUInt32LE(rate * 2 * channels, 28); header.writeUInt16LE(2 * channels, 32); header.writeUInt16LE(16, 34);
header.write('data', 36); header.writeUInt32LE(pcm.length, 40);
fs.writeFileSync(path.join(folder, 'preview.wav'), Buffer.concat([header, pcm]));
const level={seconds,channels,sampleRate:rate,normalized:normalize,inputRange:[min,max],gain,
 outputRange:[min*gain,max*gain],peakTarget:normalize?1:null,
 flashSha256:createHash('sha256').update(parseHex(fs.readFileSync(path.join(folder,'synth.hex'),'utf8'))).digest('hex'),
 wavSha256:createHash('sha256').update(Buffer.concat([header,pcm])).digest('hex'),
 maxIsrCycles:renderer.core.maxIRQ,lostIrq:renderer.core.lost};
if(normalize)fs.writeFileSync(path.join(folder,'preview-level.json'),JSON.stringify(level,null,2)+'\n');
console.log(JSON.stringify(level));
