import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const receipt='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/c-numeric-transition.json';
const polynomialReceipt='Codecs/LPX/research/lsf-compact-2026-11-10/source-transition.json';
const interpolationReceipt='Codecs/LPX/research/lpc-interpolation-2026-11-13/source-transition.json';

// Old timing receipts remain bound to their original source. A separate,
// numeric transition proves identical fixed ASM images at 0320c101. The later
// polynomial transition has its own size/timing/output evidence. Neither
// transition relabels an old timing value as a measurement of current code.
export function assertLpxRecordedSource(path,expected,encoding='text-lf'){
  const bytes=read(path);
  const actual=sha(encoding==='raw'?bytes:bytes.toString('utf8').replaceAll('\r\n','\n'));
  if(actual===expected)return;
  const field=encoding==='raw'?'raw_sha256':'text_lf_sha256';
  let recorded=expected;
  const numeric=JSON.parse(read(receipt)),source=numeric.sources[path];
  if(source?.baseline?.[field]===recorded){
    assert.equal(numeric.baseline_revision,'393b2de271568890d7b483f7602a2f59452d1a68');
    assert.equal(numeric.complete,true);
    assert.equal(numeric.asm_equivalence.all_binaries_exact,true);
    assert.equal(numeric.asm_equivalence.images,18);
    recorded=source.current[field];
  }
  if(recorded!==actual){
    const polynomial=JSON.parse(read(polynomialReceipt));
    const change=polynomial.sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(polynomial.baseline_revision,'0320c1014618188a3121fdfef0be55b30690d977');
      assert.equal(polynomial.complete,true);
      assert.equal(polynomial.all_measured_no_speed_loss,true);
      assert.equal(polynomial.all_measured_no_program_growth,true);
      assert.equal(polynomial.all_fixed_native_exact,true);
      assert.equal(polynomial.float_binary_exact,true);
      assert.equal(polynomial.fresh_universal_tiny_cases,22);
      assert.equal(polynomial.fresh_mega_cases,8);
      assert.equal(polynomial.fresh_website_tiny_cases,9);
      assert.equal(polynomial.identical_nano_images,9);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const interpolation=JSON.parse(read(interpolationReceipt));
    assert.equal(interpolation.baseline_revision,'e0939e89d88e4d91e9e441310f504ddbfd5581aa');
    assert.equal(interpolation.complete,true);
    assert.equal(interpolation.all_fixed_native_exact,true);
    assert.equal(interpolation.all_avr_corpus_exact_without_slowdown,true);
    assert.equal(interpolation.identical_asm_images,44);
    const change=interpolation.sources[path] ?? interpolation.validation_sources[path];
    assert.ok(change,path);
    assert.equal(change.baseline[field],recorded,path+' interpolation baseline');
    recorded=change.current[field];
  }
  assert.equal(recorded,actual,path+' current source');
}
