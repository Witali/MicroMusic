// Restore local lookups used by historical reports after privacy redaction.
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';

const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--repository')) {
  throw new Error('Usage: node tools/setup-history-references.mjs [--repository <path>]');
}
const repository = args.length ? resolve(args[1]) : fileURLToPath(new URL('..', import.meta.url));
const git = (...args) => execFileSync('git', ['--no-replace-objects', '-C', repository, ...args], {
  encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
});
const map = JSON.parse(readFileSync(new URL('history-redaction-20261101.json', import.meta.url), 'utf8'));
if (map.schema !== 'micromusic-history-redaction-v1') throw new Error('Unknown history map schema');
const refs = new Map(git('for-each-ref', '--format=%(refname) %(objectname)').trim().split('\n')
  .filter(Boolean).map(line => line.split(' ')));
const planned = new Map();
const add = (ref, target) => {
  const existing = refs.get(ref) ?? planned.get(ref);
  if (existing && existing !== target) throw new Error(`Conflicting local reference: ${ref}`);
  if (!existing) planned.set(ref, target);
};
let retained = 0;
for (const [original, sanitized] of Object.entries(map.commitMap)) {
  if (![original, sanitized].every(id => /^[0-9a-f]{40}$/.test(id)) || original === sanitized) {
    throw new Error('Invalid history mapping');
  }
  try { git('cat-file', '-e', `${sanitized}^{commit}`); }
  catch { throw new Error('Sanitized history is missing; fetch the full branch before running setup'); }
  let present = false;
  try { git('cat-file', '-e', `${original}^{commit}`); present = true; } catch {}
  if (present) { retained++; continue; }
  add(`refs/replace/${original}`, sanitized);
  const aliases = map.aliases[original];
  if (!Array.isArray(aliases) || !aliases.length) throw new Error('Missing historical aliases');
  for (const alias of aliases) {
    if (!/^[0-9a-f]{7,39}$/.test(alias) || !original.startsWith(alias)) throw new Error('Invalid historical alias');
    // Tags point to real sanitized objects so fsck remains valid.
    add(`refs/tags/${alias}`, sanitized);
  }
}
if (planned.size) execFileSync('git', ['--no-replace-objects', '-C', repository, 'update-ref', '--stdin'], {
  input: `start\n${[...planned].map(([ref, target]) => `create ${ref} ${target}\n`).join('')}prepare\ncommit\n`,
  encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'],
});
console.log(JSON.stringify({createdLocalReferences: planned.size,originalRevisionsAlreadyPresent: retained}));
