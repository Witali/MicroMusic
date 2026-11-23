import { readFile, stat, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { createEncoder } from '../lpx/encoder.js';
import { parseHeader, MAX_SAMPLES } from '../lpx/codec.js';

// This CLI deliberately accepts prepared PCM16 WAV. Browser audio import and
// resampling remain in the existing converter; encoding uses the same C++ WASM.
export function readPcm16Wav(bytes) {
  const input = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const text = (at, n) => String.fromCharCode(...bytes.subarray(at, at + n));
  if (bytes.length < 12 || text(0, 4) !== 'RIFF' || text(8, 4) !== 'WAVE'
      || input.getUint32(4, true) + 8 !== bytes.length) throw new Error('Expected a complete RIFF/WAVE file.');
  let format, data;
  for (let at = 12; at < bytes.length;) {
    if (at + 8 > bytes.length) throw new Error('Truncated WAV chunk.');
    const length = input.getUint32(at + 4, true), start = at + 8, end = start + length;
    if (end > bytes.length) throw new Error('Truncated WAV chunk.');
    if (text(at, 4) === 'fmt ') {
      if (format || length < 16) throw new Error('Invalid WAV format chunk.');
      format = [input.getUint16(start, true), input.getUint16(start + 2, true),
        input.getUint32(start + 4, true), input.getUint32(start + 8, true),
        input.getUint16(start + 12, true), input.getUint16(start + 14, true)];
    } else if (text(at, 4) === 'data') {
      if (data) throw new Error('Multiple WAV data chunks are unsupported.');
      data = [start, length];
    }
    at = end + (length & 1);
    if (at > bytes.length) throw new Error('Missing WAV chunk padding.');
  }
  if (!format || format.join(',') !== '1,1,8000,16000,2,16' || !data || !data[1] || data[1] & 1)
    throw new Error('Presets require mono 8000 Hz PCM16 WAV; resample the source first.');
  const count = data[1] / 2;
  if (count > MAX_SAMPLES) throw new Error('WAV exceeds the encoder sample limit.');
  return Int16Array.from({ length: count }, (_, i) => input.getInt16(data[0] + i * 2, true));
}

export async function main(args = process.argv.slice(2)) {
  const { values, positionals } = parseArgs({ args, allowPositionals: true, options: {
    kbps: { type: 'string' }, backend: { type: 'string', default: 'scalar' }
  } });
  const [input, output] = positionals, kbps = Number(values.kbps);
  if (positionals.length !== 2 || ![3, 8].includes(kbps) || !['scalar', 'simd'].includes(values.backend)
      || resolve(input) === resolve(output))
    throw new Error('Usage: node web-player/scripts/encode-lpx.mjs input-8khz.wav new-output.lpx --kbps 3|8 [--backend scalar|simd]');
  // Refuse an existing destination before any expensive analysis. The final
  // exclusive creation also protects against a destination created meanwhile.
  try { await stat(output); throw new Error('Output already exists.'); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const size = (await stat(input)).size;
  if (size > MAX_SAMPLES * 2 + 1024 * 1024) throw new Error('WAV exceeds the input size limit.');
  const pcm = readPcm16Wav(await readFile(input));
  const name = values.backend === 'simd' ? 'encoder-adaptive-simd.wasm' : 'encoder-adaptive.wasm';
  const encode = await createEncoder(await readFile(new URL('../lpx/' + name, import.meta.url)));
  const bytes = encode(pcm, 8000, kbps), info = parseHeader(bytes);
  const cap = Math.floor(pcm.length * kbps * 1000 / (8 * 8000));
  if (bytes.length > cap || info.samples !== pcm.length || info.sampleRate !== 8000)
    throw new Error('Encoded stream failed its complete-file budget or sample count.');
  await writeFile(output, bytes, { flag: 'wx' });
  console.log(JSON.stringify({ format: info.format, targetKbps: kbps, wireProfile: info.profile,
    samples: info.samples, sampleRate: info.sampleRate, bytes: bytes.length, completeByteCap: cap,
    fileBitrateBps: info.bitrate, backend: values.backend }));
  return bytes;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href)
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
