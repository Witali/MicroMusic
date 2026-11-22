import { readFile, stat, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createDecoder, encodeWav, MAX_FILE_BYTES } from '../lpx/codec.js';

const [input, output, ...extra] = process.argv.slice(2);
if (!input || !output || extra.length || resolve(input) === resolve(output)) throw new Error('Usage: node web-player/scripts/decode-lpx.mjs input.lpx new-output.wav');
const size = (await stat(input)).size;
if (size < 13 || size > MAX_FILE_BYTES) throw new Error('LPX file must contain 13 bytes to 100 MiB.');
const decode = await createDecoder(await readFile(new URL('../lpx/decoder.wasm', import.meta.url)));
const result = decode(await readFile(input));
await writeFile(output, new Uint8Array(encodeWav(result.pcm, result.sampleRate)), { flag: 'wx' });
console.log(`${result.format}: ${result.samples} samples at ${result.sampleRate} Hz → PCM16 WAV`);
