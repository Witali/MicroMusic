// Render the actual AVR image through the player's default filters at 48 kHz.
// Web Audio's default BiquadFilter Q is 1 dB; use the same RBJ coefficients.
import fs from 'node:fs';
import path from 'node:path';
import { Renderer } from '../web-player/lib/renderer.js';
const folder = process.argv[2], seconds = Number(process.argv[3] || 14);
if (!folder || !Number.isFinite(seconds) || seconds <= 0 || seconds > 300)
  throw new Error('Usage: node tools/render-firmware-preview.mjs firmware-folder [seconds]');
const rate = 48000, renderer = new Renderer({pwmHz: 37500,
  flashHex: fs.readFileSync(path.join(folder, 'synth.hex'), 'utf8'),
  eepromHex: fs.readFileSync(path.join(folder, 'eeprom.hex'), 'utf8')}, rate);
function biquad(type, frequency) {
  const w = 2 * Math.PI * frequency / rate, cos = Math.cos(w), alpha = Math.sin(w) / (2 * 10 ** (1 / 20));
  const a0 = 1 + alpha, b0 = (type === 'highpass' ? 1 + cos : 1 - cos) / 2;
  const b1 = type === 'highpass' ? -(1 + cos) : 1 - cos;
  const a1 = -2 * cos / a0, a2 = (1 - alpha) / a0;
  let z1 = 0, z2 = 0;
  return x => { const y = b0 / a0 * x + z1; z1 = b1 / a0 * x - a1 * y + z2; z2 = b0 / a0 * x - a2 * y; return y; };
}
const high = biquad('highpass', 35), low = biquad('lowpass', 9000);
const count = Math.round(seconds * rate), pcm = Buffer.alloc(count * 2);
let min = 0, max = 0;
for (let start = 0; start < count; start += 4096) {
  const block = renderer.render(Math.min(4096, count - start));
  for (let j = 0; j < block.length; j++) {
    const y = low(high(block[j])) * .65; min = Math.min(min, y); max = Math.max(max, y);
    if (Math.abs(y) >= 1) throw new Error('Preview clipped');
    pcm.writeInt16LE(Math.round(y * 32767), (start + j) * 2);
  }
}
const header = Buffer.alloc(44); header.write('RIFF'); header.writeUInt32LE(36 + pcm.length, 4); header.write('WAVEfmt ', 8);
header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22); header.writeUInt32LE(rate, 24);
header.writeUInt32LE(rate * 2, 28); header.writeUInt16LE(2, 32); header.writeUInt16LE(16, 34);
header.write('data', 36); header.writeUInt32LE(pcm.length, 40);
fs.writeFileSync(path.join(folder, 'preview.wav'), Buffer.concat([header, pcm]));
console.log(JSON.stringify({seconds, sampleRate: rate, min, max, maxIsrCycles: renderer.core.maxIRQ, lostIrq: renderer.core.lost}));
