import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = new URL('../../', import.meta.url);
const receipt = JSON.parse(readFileSync(new URL('research/web-encoder-cuda-2026-11-23/kernel-validation.json', root)));
test('CUDA validation receipt binds the exact kernel and independent test sources', () => {
  assert.equal(receipt.checks, 4461); assert.equal(receipt.parameterTuples, 24741);
  assert.equal(receipt.rejectedInvalidJobs, 10);
  assert.ok(receipt.flags.includes('--fmad=false'));
  assert.ok(receipt.flags.includes('-DLPX_ENCODER_ENABLE_CUDA=1'));
  for (const [path, expected] of Object.entries(receipt.sourceSha256)) {
    const text = readFileSync(new URL(path, root), 'utf8').replaceAll('\r\n', '\n');
    assert.equal(createHash('sha256').update(text).digest('hex'), expected, path);
  }
});

const executable = process.env.LPX_CUDA_SELFTEST;
test('actual CUDA hardware retains every scalar winner, pulse, loss and state',
  { skip: !executable || !existsSync(executable) }, () => {
    const result = spawnSync(executable, [], { cwd: fileURLToPath(root), encoding: 'utf8', windowsHide: true });
    assert.equal(result.status, 0, result.stderr || result.stdout);
    const actual = JSON.parse(result.stdout.trim());
    assert.equal(actual.checks, 4461); assert.equal(actual.tuples, 24741);
    assert.equal(actual.rejectedInvalidJobs, 10); assert.equal(actual.exact, true);
  });
