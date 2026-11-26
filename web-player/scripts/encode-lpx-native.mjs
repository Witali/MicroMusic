// Binary-safe file frontend. The encoder itself is shared C++, with no Python.
import { spawn } from 'node:child_process';
import { readFile, stat, open, unlink } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const MAX_PCM_BYTES = 32_000_000 * 2;
const { values, positionals, tokens } = parseArgs({ allowPositionals: true, tokens: true, options: {
  encoder: { type: 'string' }, pcm: { type: 'boolean', default: false },
  profile: { type: 'string', default: '6' }, rate: { type: 'string', default: '8000' },
  accuracy: { type: 'string' }, legacy: { type: 'boolean', default: false }, help: { type: 'boolean', default: false },
  backend: { type: 'string', default: 'cpu' }, quality: { type: 'string', default: 'adaptive' },
  'quality-target': { type: 'string', default: 'pwm' },
  search: { type: 'string', default: 'expanded' }, 'size-allowance': { type: 'string', default: '0' },
  calls: { type: 'string', default: '4' }, 'max-bytes': { type: 'string', default: '0' },
  repeat: { type: 'string', default: '1' }, 'auto-quiet': { type: 'boolean', default: false },
  normalize: { type: 'boolean', default: false }, 'target-lufs': { type: 'string', default: '-18' }, 'max-gain-db': { type: 'string', default: '12' },
  'non-speech': { type: 'boolean', default: false }, ffmpeg: { type: 'string', default: 'ffmpeg' },
  ffprobe: { type: 'string', default: 'ffprobe' }
} });
const root = fileURLToPath(new URL('../../', import.meta.url));
const [source, destination] = positionals;
const usage = 'Usage: node web-player/scripts/encode-lpx-native.mjs input-audio new-output.lpx [--accuracy 3|4|6|8 | --profile 3|4|6|8] [--encoder executable] [--pcm] [--backend cpu|cuda] [--quality fast|adaptive] [--quality-target pcm|pwm]';
if (values.help) {
  console.log(`${usage}\nDefault: the shared Web UI accuracy engine, level 6; --profile is an alias.\nLegacy compatibility: --legacy --profile 4|6 [--search expanded|reference] [--size-allowance 0..100] [--max-bytes N] [--auto-quiet] [--non-speech].`);
  process.exit(0);
}
if (positionals.length !== 2 || !source || !destination || resolve(source) === resolve(destination)) {
  throw new Error(usage);
}
const specified = new Set(tokens.filter(token => token.kind === 'option').map(token => token.name));
const level = values.accuracy ?? values.profile;
if (values.legacy) {
  if (specified.has('accuracy')) throw new Error('--accuracy cannot be combined with --legacy; use --legacy --profile 4|6.');
  if (!['4', '6'].includes(values.profile)) throw new Error('Legacy profile must be 4 or 6.');
} else {
  if (['search', 'size-allowance', 'max-bytes', 'auto-quiet', 'non-speech'].some(name => specified.has(name)))
    throw new Error('--search, --size-allowance, --max-bytes, --auto-quiet and --non-speech require --legacy.');
  if (specified.has('profile') && specified.has('accuracy') && values.profile !== values.accuracy)
    throw new Error('--profile and --accuracy must select the same accuracy level.');
  if (!['3', '4', '6', '8'].includes(level)) throw new Error('Accuracy level must be 3, 4, 6 or 8.');
}
if (!['8000', '12000', '16000'].includes(values.rate)
    || !['cpu', 'cuda'].includes(values.backend) || !['fast', 'adaptive'].includes(values.quality)
    || !['pcm', 'pwm'].includes(values['quality-target'])
    || !['expanded', 'reference'].includes(values.search)) throw new Error('Invalid encoding options.');
if (!/^[0-4]$/.test(values.calls) || !/^(?:[1-9]|1[0-9]|20)$/.test(values.repeat)
    || !/^\d+$/.test(values['max-bytes']) || Number(values['max-bytes']) > 104857600
    || (Number(values['max-bytes']) !== 0 && Number(values['max-bytes']) < 22)) throw new Error('Invalid refinement, repeat or byte budget.');
if (!/^\d+$/.test(values['size-allowance']) || Number(values['size-allowance']) > 100) throw new Error('Size allowance must be in 0..100 percent.');
if (values.legacy && values.quality === 'fast' && (values.search !== 'expanded' || Number(values['size-allowance']) !== 0
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
  const args = [...(values.legacy ? ['--legacy', '--profile', values.profile] : ['--accuracy', level]),
    '--rate', values.rate, '--backend', values.backend, '--quality', values.quality,
    '--calls', values.calls, '--repeat', values.repeat,
    ...(specified.has('quality-target') ? ['--quality-target', values['quality-target']] : []),
    ...(values.legacy ? ['--search', values.search, '--size-allowance', values['size-allowance'], '--max-bytes', values['max-bytes'],
      ...(values['auto-quiet'] ? ['--auto-quiet'] : []), ...(values['non-speech'] ? ['--non-speech'] : [])] : []),
    ...(values.normalize ? ['--normalize','--target-lufs',values['target-lufs'],'--max-gain-db',values['max-gain-db']] : [])];
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
