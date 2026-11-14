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
const lpcShortReport='Codecs/LPX/research/tiny-lpc-short-2026-11-13/';
const q14Report='Codecs/LPX/research/tiny-q14-2026-11-13/';
const lsfNeighborsReport='Codecs/LPX/research/tiny-lsf-neighbors-2026-11-13/';
const megaLsfReport='Codecs/LPX/research/mega-lsf-wide-2026-11-13/';
const tinyPitchReport='Codecs/LPX/research/tiny-v9-pulse-pitch-2026-11-13/';
const tinySharedPqReport='Codecs/LPX/research/tiny-v9-shared-pq-2026-11-13/';
const tinySubframeReport='Codecs/LPX/research/tiny-v9-subframe-2026-11-13/';
const tinyOddPhaseReport='Codecs/LPX/research/tiny-v9-odd-phase-2026-11-13/';
const tinyLpcHalfReport='Codecs/LPX/research/tiny-v9-lpc-half-2026-11-13/';

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
  for(const [directory,revision] of [
    [lpcPairsReport,'84de5ce411a1ace1b29a732f0998c10f67f3e53f'],
    [lpcShortReport,'26faf77221d4259eda9859b545e2ed25b12b898a'],
    [q14Report,'dc522dea665e544aebc95b550a7789186e7bec0d'],
    [lsfNeighborsReport,'b4a9757364280049ec7cd2504c8fddfff3a56900'],
  ]){
    if(recorded===actual)break;
    const report=JSON.parse(read(directory+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.baseline_revision,revision);
      assert.equal(report.universal_irq_cases,22);
      assert.equal(report.identical_fixed_header_images,9);
      const evidence=read(directory+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const report=JSON.parse(read(megaLsfReport+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.baseline_revision,'ddefa0c4ffcc18cf16e659fa0ab3652f1f7dca84');
      assert.equal(report.mega_asm_irq_cases,6);
      assert.equal(report.identical_mega_c_images,4);
      assert.equal(report.identical_nano_images,9);
      const evidence=read(megaLsfReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const report=JSON.parse(read(tinyPitchReport+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.complete,true);
      assert.equal(report.baseline_revision,'65c3073e354b9956d252c7d118e40ddaae19dd83');
      assert.equal(report.universal_irq_cases,22);
      assert.equal(report.identical_web_images,18);
      const evidence=read(tinyPitchReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const report=JSON.parse(read(tinySharedPqReport+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.complete,true);
      assert.equal(report.baseline_revision,'c391ad095b5ca6c79ef27add0471029a33a6c88c');
      assert.equal(report.universal_irq_cases,22);
      assert.equal(report.identical_web_images,18);
      const evidence=read(tinySharedPqReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const report=JSON.parse(read(tinySubframeReport+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.complete,true);
      assert.equal(report.baseline_revision,'9760ff7f76e66ff6325752fd15278e144bbf0598');
      assert.equal(report.universal_irq_cases,22);
      assert.equal(report.identical_web_images,18);
      const evidence=read(tinySubframeReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const report=JSON.parse(read(tinyOddPhaseReport+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.complete,true);
      assert.equal(report.baseline_revision,'703174249a5dba87cc796174edc2598bcbd24652');
      assert.equal(report.universal_irq_cases,22);
      assert.equal(report.identical_web_images,18);
      const evidence=read(tinyOddPhaseReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  if(recorded!==actual){
    const report=JSON.parse(read(tinyLpcHalfReport+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.complete,true);
      assert.equal(report.baseline_revision,'c415ab84c5e00a77c36eb10a5c4b6384c172c068');
      assert.equal(report.universal_irq_cases,22);
      assert.equal(report.identical_web_images,18);
      const evidence=read(tinyLpcHalfReport+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  assert.equal(recorded,actual,path+' current source');
}
