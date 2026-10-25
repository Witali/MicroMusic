import test from 'node:test';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

test('2 / 2.5 MHz voice ROMs: full C reference, source duration, retimed startup, CRC faults and every PWM branch', () => {
  const run = (name,...args) => execFileSync(process.execPath,[fileURLToPath(new URL(name,import.meta.url)),...args,'--check']);
  run('clock-audit.mjs');
  for (const hz of [2000000,2500000]) for (const profile of ['balloon','owl'])
    run('timing-check.mjs','--cpu-hz',String(hz),'--profile',profile);
});
