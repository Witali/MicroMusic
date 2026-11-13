import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';

const root=new URL('../../../',import.meta.url);
const read=path=>readFileSync(new URL(path,root));
const sha=data=>createHash('sha256').update(data).digest('hex');
const receipt='Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/c-numeric-transition.json';
const polynomialReceipt='Codecs/LPX/research/lsf-compact-2026-11-10/source-transition.json';
const interpolationReceipt='Codecs/LPX/research/lpc-interpolation-2026-11-13/source-transition.json';
const spectrumReport='Codecs/LPX/research/tiny-spectrum-anchors-2026-11-13/';
const parserReport='Codecs/LPX/research/tiny-parser-2026-11-13/';
const lpcPairsReport='Codecs/LPX/research/tiny-lpc-pairs-2026-11-13/';

// Follow measured source transitions while retaining the original timing receipts.
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
    const change=interpolation.sources[path] ?? interpolation.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(interpolation.baseline_revision,'e0939e89d88e4d91e9e441310f504ddbfd5581aa');
      assert.equal(interpolation.complete,true);
      assert.equal(interpolation.all_fixed_native_exact,true);
      assert.equal(interpolation.all_avr_corpus_exact_without_slowdown,true);
      assert.equal(interpolation.identical_asm_images,44);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const spectrum=JSON.parse(read(spectrumReport+'source-transition.json'));
    const change=spectrum.sources[path] ?? spectrum.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(spectrum.baseline_revision,'de98d64162368cf3b6104907076a7e1c3d3f3f17');
      const evidence=read(spectrumReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),spectrum.measurements_sha256);
      assert.equal(spectrum.complete,true);
      assert.equal(spectrum.universal_irq_cases,22);
      assert.equal(spectrum.identical_fixed_header_images,9);
      recorded=change.current[field];
    }
  }
  for(const step of ['read-bits','rice']){
    if(recorded===actual)break;
    const parser=JSON.parse(read(parserReport+step+'-transition.json'));
    const change=parser.sources[path] ?? parser.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(parser.step,step);
      assert.equal(parser.complete,true);
      assert.equal(parser.universal_irq_cases,22);
      assert.equal(parser.identical_fixed_header_images,9);
      const evidence=read(parserReport+step+'.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),parser.measurements_sha256);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const pairs=JSON.parse(read(lpcPairsReport+'source-transition.json'));
    const change=pairs.sources[path] ?? pairs.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(pairs.baseline_revision,'84de5ce411a1ace1b29a732f0998c10f67f3e53f');
      assert.equal(pairs.universal_irq_cases,22);
      assert.equal(pairs.identical_fixed_header_images,9);
      const evidence=read(lpcPairsReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),pairs.measurements_sha256);
      recorded=change.current[field];
    }
  }
  assert.equal(recorded,actual,path+' current source');
}
