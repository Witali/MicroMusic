import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Script } from 'node:vm';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

test('Standalone build matches source, parses as classic JS, and needs no external scripts/styles', () => {
  execFileSync(process.execPath, [fileURLToPath(new URL('../scripts/build-standalone.mjs', import.meta.url)), '--check']);
  const html = readFileSync(new URL('../Intel_8080_ROM_Player.html', import.meta.url), 'utf8');
  assert.doesNotMatch(html, /<script[^>]+src=/i); assert.doesNotMatch(html, /<link[^>]+rel="stylesheet"/i);
  assert.doesNotMatch(html, /<audio\b/i);
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 1); assert.doesNotThrow(() => new Script(scripts[0][1]));
  const source = JSON.parse(readFileSync(new URL('../SOURCE.json', import.meta.url), 'utf8'));
  for (const name of ['uniform26.bin', 'balanced27.bin', 'diagnostic_dualcrc.bin']) {
    const original = source.files.find(row => row.path === name);
    assert.equal(createHash('sha256').update(readFileSync(new URL('./roms/' + name, import.meta.url))).digest('hex'), original.sha256);
  }
});
