import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import assert from 'node:assert/strict';
import { runCpmTest } from './run-cpm-test.mjs';

// Download the four original COMs from the publisher into an external/ignored
// directory first. Never fetch or execute a substituted binary implicitly.
const directory = process.argv[2];
if (!directory) throw Error('Usage: node run-exercisers.mjs external-directory [report.json]');
const reference = JSON.parse(readFileSync(new URL('../EXERCISERS.json', import.meta.url)));
const reports = [];
for (const expected of reference.tests) {
  const path = join(directory, expected.name), data = readFileSync(path);
  assert.equal(createHash('sha256').update(data).digest('hex'), expected.sha256, expected.name + ' SHA-256');
  process.stdout.write(`Running ${expected.name}…\n`);
  const result = runCpmTest(path);
  assert.equal(result.reached_exit, true, expected.name);
  assert.equal(result.instructions, expected.instructions, expected.name + ' instructions');
  assert.equal(result.t_states, expected.t_states, expected.name + ' T-states');
  assert.equal(result.output.replace(/\r/g, ''), expected.output.replace(/\r/g, ''), expected.name + ' console results');
  reports.push(result);
  console.log(`PASS ${expected.name}: ${result.instructions} instructions, ${result.t_states} T`);
}
if (process.argv[3]) writeFileSync(process.argv[3], JSON.stringify({ ...reference, tests: reports }, null, 2) + '\n');
