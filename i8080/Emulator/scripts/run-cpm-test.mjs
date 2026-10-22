import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { CPU8080 } from '../core8080.mjs';

// Minimal CP/M console harness. Test binaries remain external and unmodified.
export function runCpmTest(path, { maxInstructions = 5000000000, onOutput = () => {} } = {}) {
  const binary = readFileSync(path), image = new Uint8Array(65536);
  if (binary.length > 0xfe00) throw Error('CP/M program does not fit');
  image.set(binary, 0x100); image[5] = 0xc9; // BDOS returns through a real emulated RET.
  const cpu = new CPU8080(image, { memoryMode: 'allram', pc: 0x100, sp: 0xf000 });
  let output = '', bdosCalls = 0;
  const started = performance.now();
  while (cpu.pc !== 0 && !cpu.halted && cpu.count < maxInstructions) {
    if (cpu.pc === 5) {
      bdosCalls++;
      let text = '';
      if (cpu.r[1] === 2) text = String.fromCharCode(cpu.r[3]);
      else if (cpu.r[1] === 9) {
        let at = cpu.pair(1), length = 0;
        while (cpu.read(at) !== 0x24 && length++ < 65536) { text += String.fromCharCode(cpu.read(at)); at = (at + 1) & 65535; }
        if (length >= 65536) throw Error('Unterminated BDOS string');
      } else if (cpu.r[1] === 0) break;
      else throw Error(`Unsupported BDOS function ${cpu.r[1]}`);
      output += text; onOutput(text);
    }
    cpu.step();
  }
  return { name: basename(path), sha256: createHash('sha256').update(binary).digest('hex'), bytes: binary.length,
    output, instructions: cpu.count, t_states: cpu.t, pc: cpu.pc, bdos_calls: bdosCalls,
    reached_exit: cpu.pc === 0, halted: cpu.halted, instruction_limit: cpu.count >= maxInstructions,
    elapsed_seconds: (performance.now() - started) / 1000 };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const path = process.argv[2]; if (!path) throw Error('Usage: node run-cpm-test.mjs external.COM [report.json]');
  const result = runCpmTest(path, { onOutput: text => process.stdout.write(text) });
  console.log('\n' + JSON.stringify({ ...result, output: undefined }, null, 2));
  if (process.argv[3]) writeFileSync(process.argv[3], JSON.stringify(result, null, 2) + '\n');
  if (!result.reached_exit || /ERROR|CPU HAS FAILED/i.test(result.output)) process.exitCode = 1;
}
