// Binary-safe file frontend. The encoder itself is shared C++, with no Python.
import { spawn } from 'node:child_process';
import { readFile, stat, open, unlink } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const MAX_PCM_BYTES = 32_000_000 * 2;
const { values, positionals } = parseArgs({ allowPositionals: true, options: {
  encoder: { type: 'string' }, pcm: { type: 'boolean', default: false },
  profile: { type: 'string', default: '6' }, rate: { type: 'string', default: '8000' },
  backend: { type: 'string', default: 'cpu' }, quality: { type: 'string', default: 'adaptive' },
  search: { type: 'string', default: 'expanded' }, 'size-allowance': { type: 'string', default: '0' },
  calls: { type: 'string', default: '4' }, 'max-bytes': { type: 'string', default: '0' },
  repeat: { type: 'string', default: '1' }, 'auto-quiet': { type: 'boolean', default: false },
  'non-speech': { type: 'boolean', default: false }, ffmpeg: { type: 'string', default: 'ffmpeg' },
  ffprobe: { type: 'string', default: 'ffprobe' }
} });
const root = fileURLToPath(new URL('../../', import.meta.url));
const [source, destination] = positionals;
if (positionals.length !== 2 || !source || !destination || resolve(source) === resolve(destination)) {
  throw new Error('Usage: node web-player/scripts/encode-lpx-native.mjs input-audio new-output.lpx [--encoder executable] [--pcm] [--backend cpu|cuda] [--quality fast|adaptive]');
}
if (!['4', '6'].includes(values.profile) || !['8000', '12000', '16000'].includes(values.rate)
    || !['cpu', 'cuda'].includes(values.backend) || !['fast', 'adaptive'].includes(values.quality)
    || !['expanded', 'reference'].includes(values.search)) throw new Error('Invalid encoding options.');
if (!/^[0-4]$/.test(values.calls) || !/^(?:[1-9]|1[0-9]|20)$/.test(values.repeat)
    || !/^\d+$/.test(values['max-bytes']) || Number(values['max-bytes']) > 104857600
    || (Number(values['max-bytes']) !== 0 && Number(values['max-bytes']) < 22)) throw new Error('Invalid refinement, repeat or byte budget.');
if (!/^\d+$/.test(values['size-allowance']) || Number(values['size-allowance']) > 100) throw new Error('Size allowance must be in 0..100 percent.');
if (values.quality === 'fast' && (values.search !== 'expanded' || Number(values['size-allowance']) !== 0
    || values.calls !== '4' || Number(values['max-bytes']) !== 0 || values['auto-quiet'] || values['non-speech'])) throw new Error('Adaptive search options require --quality adaptive.');
try { await stat(destination); throw new Error('Output already exists; choose a new output path.'); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
const cancellation = new AbortController();
const cancel = () => cancellation.abort();
process.once('SIGINT', cancel); process.once('SIGTERM', cancel);
function collect(command, args, input, limit) {
  return new Promise((accept, reject) => {
    let child;
    try { child = spawn(command, args, { stdio: ['pipe', 'pipe', 'pipe'], signal: cancellation.signal, windowsHide: true }); }
    catch (error) { reject(error); return; }
    const chunks = [], errors = []; let bytes = 0, errorBytes = 0, overflow = false, failure;
    child.on('error', error => { failure = error; });
    child.stdout.on('data', chunk => {
      bytes += chunk.length;
      if (bytes > limit) { overflow = true; child.kill(); return; }
      chunks.push(chunk);
    });
    child.stderr.on('data', chunk => { errorBytes += chunk.length; if (errorBytes <= 65536) errors.push(chunk); });
    // A rejected CUDA request may close stdin before the PCM has been sent.
    child.stdin.on('error', error => { if (error.code !== 'EPIPE') failure = error; });
    child.on('close', code => {
      if (cancellation.signal.aborted) return reject(new Error('Encoding cancelled; no output file was written.'));
      if (overflow) return reject(new Error('Audio exceeds the 32 000 000-sample limit or process output limit.'));
      if (failure) return reject(failure);
      if (code !== 0) {
        let message = 'Audio conversion or native encoding failed.';
        try { message = JSON.parse(Buffer.concat(errors).toString()).error || message; } catch {}
        return reject(new Error(message));
      }
      accept({ bytes: Buffer.concat(chunks), stderr: Buffer.concat(errors).toString() });
    });
    child.stdin.end(input);
  });
}
try {
  let pcm;
  if (values.pcm) {
    const input = await stat(source);
    if (!input.size || input.size > MAX_PCM_BYTES || input.size % 2) throw new Error('Expected 1..32 000 000 mono PCM16 little-endian samples.');
    pcm = await readFile(source);
  } else {
    const probe = await collect(values.ffprobe, ['-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=channels', '-of', 'json', resolve(source)], undefined, 65536);
    const channels = JSON.parse(probe.bytes.toString()).streams?.[0]?.channels;
    if (!Number.isInteger(channels) || channels < 1 || channels > 64) throw new Error('Cannot identify a supported audio stream.');
    const mix = Array.from({ length: channels }, (_, index) => `${(1 / channels).toPrecision(17)}*c${index}`).join('+');
    const conversion = await collect(values.ffmpeg, ['-v', 'error', '-i', resolve(source), '-map', '0:a:0', '-vn',
      '-af', `pan=mono|c0=${mix}`, '-ar', values.rate, '-dither_method', 'none', '-acodec', 'pcm_s16le', '-f', 's16le', 'pipe:1'], undefined, MAX_PCM_BYTES);
    pcm = conversion.bytes;
    if (!pcm.length || pcm.length % 2) throw new Error('Audio conversion produced no complete PCM16 samples.');
  }
  const executable = values.encoder || resolve(root, 'build/lpx-native',
    `lpx-encode${values.backend === 'cuda' ? '-cuda' : ''}${process.platform === 'win32' ? '.exe' : ''}`);
  const args = ['--profile', values.profile, '--rate', values.rate, '--backend', values.backend,
    '--quality', values.quality, '--search', values.search, '--size-allowance', values['size-allowance'],
    '--calls', values.calls, '--max-bytes', values['max-bytes'], '--repeat', values.repeat,
    ...(values['auto-quiet'] ? ['--auto-quiet'] : []), ...(values['non-speech'] ? ['--non-speech'] : [])];
  const result = await collect(executable, args, pcm, 100 * 1024 * 1024);
  if (result.bytes.length < 13 || result.bytes.subarray(0, 2).toString() !== 'L9') throw new Error('Native encoder returned no LPX V9 stream.');
  if (cancellation.signal.aborted) throw new Error('Encoding cancelled; no output file was written.');
  let output;
  try {
    output = await open(destination, 'wx');
    await output.writeFile(result.bytes);
    if (cancellation.signal.aborted) throw new Error('Encoding cancelled; no output file was written.');
    await output.close(); output = undefined;
  } catch (error) {
    if (output) { await output.close().catch(() => {}); await unlink(destination).catch(() => {}); }
    throw error;
  }
  if (result.stderr.trim()) console.log(result.stderr.trim());
} finally {
  process.removeListener('SIGINT', cancel); process.removeListener('SIGTERM', cancel);
}
