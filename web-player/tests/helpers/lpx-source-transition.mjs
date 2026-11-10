import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const receipt='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/c-numeric-transition.json';

// Old timing receipts remain bound to their original source. A separate,
// measured transition proves the current fixed ASM images are identical;
// fresh C/float checks are recorded independently, never substituted for old runs.
export function assertLpxRecordedSource(path,expected,encoding='text-lf'){
  const bytes=read(path);
  const actual=sha(encoding==='raw'?bytes:bytes.toString('utf8').replaceAll('\r\n','\n'));
  if(actual===expected)return;
  const transition=JSON.parse(read(receipt));
  assert.equal(transition.baseline_revision,'393b2de271568890d7b483f7602a2f59452d1a68');
  assert.equal(transition.complete,true);
  const source=transition.sources[path];assert.ok(source,path);
  const field=encoding==='raw'?'raw_sha256':'text_lf_sha256';
  assert.equal(source.baseline[field],expected,path+' historical source');
  assert.equal(source.current[field],actual,path+' current source');
  assert.equal(transition.asm_equivalence.all_binaries_exact,true);
  assert.equal(transition.asm_equivalence.images,18);
}
