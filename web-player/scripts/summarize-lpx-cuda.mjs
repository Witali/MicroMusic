// Export aggregate numerical measurements only. Never copy corpus fingerprints,
// per-recording identifiers, source paths, book names or speaker metadata.
import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
const { values } = parseArgs({ options: { input: { type: 'string' }, warm: { type: 'string' },
  adaptive: { type: 'string' }, output: { type: 'string' } } });
if (!values.input || !values.output) throw new Error('Pass --input <private benchmark> --output <aggregate JSON>.');
const load = path => {
  const value = JSON.parse(readFileSync(path));
  if (value.schema !== 'lpx-cuda-private-benchmark-v1' || !value.rows.length || value.rows.some(x => !x.exact)) throw new Error('Expected successful CPU/CUDA benchmark.');
  return value;
};
const sum = a => a.reduce((s, x) => s+x, 0);
const median = a => { const s = [...a].sort((x, y) => x-y); return (s[Math.floor((s.length-1)/2)] + s[Math.floor(s.length/2)])/2; };
function summary(value) {
  const inputs = [...new Map(value.rows.map(x => [x.ordinal, x])).values()];
  return { quality: value.quality, inputs: inputs.length, profileCases: value.rows.length,
    totalInputSamples: sum(inputs.map(x => x.samples)), sampleRate: 8000,
    maxInputSamples: Math.max(...inputs.map(x => x.samples)),
    continuousLongInputs: inputs.filter(x => x.samples > 64000).length,
    allLpxBytesEqual: true,
    profiles: [4, 6].filter(profile => value.rows.some(x => x.profile === profile)).map(profile => {
      const rows = value.rows.filter(x => x.profile === profile);
      const cpu = sum(rows.map(x => x.runs.cpu.encodingMs)), cuda = sum(rows.map(x => x.runs.cuda.encodingMs));
      const warm = rows.filter(x => Number.isFinite(x.runs.cpu.warmMedianMs) && Number.isFinite(x.runs.cuda.warmMedianMs));
      return { profile, cases: rows.length, firstEncodingTotalMs: { cpu, cuda }, firstEncodingTotalRatio: cpu/cuda,
        medianFirstEncodingRatio: median(rows.map(x => x.runs.cpu.encodingMs/x.runs.cuda.encodingMs)),
        coldProcessTotalMs: { cpu: sum(rows.map(x => x.wallMs.cpu)), cuda: sum(rows.map(x => x.wallMs.cuda)) },
        medianColdProcessRatio: median(rows.map(x => x.wallMs.cpu/x.wallMs.cuda)),
        warmCases: warm.length,
        medianWarmEncodingRatio: warm.length ? median(warm.map(x => x.runs.cpu.warmMedianMs/x.runs.cuda.warmMedianMs)) : null,
        minWarmEncodingRatio: warm.length ? Math.min(...warm.map(x => x.runs.cpu.warmMedianMs/x.runs.cuda.warmMedianMs)) : null,
        maxWarmEncodingRatio: warm.length ? Math.max(...warm.map(x => x.runs.cpu.warmMedianMs/x.runs.cuda.warmMedianMs)) : null };
    }) };
}
const measured = load(values.input);
const gpu = measured.gpu.split(/\r?\n/)[0].split(',').map(x => x.trim());
if (gpu.length !== 4 || !gpu[0].startsWith('NVIDIA') || !/^\d+\.\d+$/.test(gpu[1]) || !/^[\d.]+$/.test(gpu[2])) throw new Error('Expected the recorded GPU name/capability/driver/memory query.');
const result = { schema: 'lpx-cuda-aggregate-benchmark-v1',
  hardware: { gpu: gpu[0], computeCapability: gpu[1], driver: gpu[2], memory: gpu[3] },
  scope: 'Measured host encoder only; each CPU/CUDA pair receives identical prepared PCM. No listening-quality, AVR timing or other-GPU speed claim.',
  timing: 'First/warm encoding includes full LPX validation but excludes backend initialization, input conversion and process startup; cold process timings include initialization and I/O.',
  corpus: summary(measured), warmSubset: values.warm ? summary(load(values.warm)) : null,
  adaptiveSubset: values.adaptive ? summary(load(values.adaptive)) : null,
  limitations: ['Cold CUDA initialization can outweigh encoding work on short or silent inputs.',
    'The fast corpus run validates full continuous inputs; the adaptive subset has separate coverage.',
    'The retained archive metadata does not substantiate hundreds of distinct speakers.'] };
writeFileSync(values.output, JSON.stringify(result, null, 2)+'\n');
console.log(JSON.stringify({ savedAggregate: true, exactCases: result.corpus.profileCases,
  firstEncodingTotalRatios: result.corpus.profiles.map(x => ({ profile: x.profile, ratio: x.firstEncodingTotalRatio })) }));
