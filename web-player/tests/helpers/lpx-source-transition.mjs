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
const webuiRebuildReceipt='Codecs/LPX/research/webui-rebuild-2026-11-14/source-transition.json';
const pulsePacketReport='Codecs/LPX/research/tiny-v9-pulse-packet-2026-11-16/';
const flashReadReport='Codecs/LPX/research/tiny-v9-flash-read-2026-11-16/';
const boundedPwmReport='Codecs/LPX/research/tiny-v9-bounded-pwm-2026-11-16/';
const unsignedInterpReport='Codecs/LPX/research/tiny-v9-unsigned-interp-2026-11-16/';
const staticRomReport='Codecs/LPX/research/tiny-v9-static-rom-2026-11-16/';
const romHeaderReport='Codecs/LPX/research/tiny-v9-rom-header-2026-11-16/';
const polySeedReport='Codecs/LPX/research/tiny-v9-poly-seed-2026-11-16/';
const p4AmplitudeReport='Codecs/LPX/research/tiny-v9-p4-amplitude-2026-11-16/';
const pulseSentinelReport='Codecs/LPX/research/tiny-v9-pulse-sentinel-2026-11-16/';
const lsfInvariantsReport='Codecs/LPX/research/tiny-v9-lsf-invariants-2026-11-16/';
const cosEdgeReport='Codecs/LPX/research/tiny-v9-cos-edge-2026-11-16/';
const q4ScaleRuntimeReport='Codecs/LPX/research/tiny-v9-q4-scale-runtime-2026-11-16/';
const lpcSaturationReport='Codecs/LPX/research/tiny-v9-lpc-saturation-2026-11-16/';
const q4SynthesisClipReport='Codecs/LPX/research/tiny-v9-q4-synthesis-clip-2026-11-16/';
const joinedBitfieldReport='Codecs/LPX/research/tiny-v9-joined-bitfield-2026-11-16/';
const oneShotBssReport='Codecs/LPX/research/tiny-v9-one-shot-bss-2026-11-16/';
const seededPolyQ8Report='Codecs/LPX/research/tiny-v9-poly-seeded-q8-2026-11-16/';
const signed6ExcitationReport='Codecs/LPX/research/tiny-v9-signed6-excitation-2026-11-16/';
const synthesisHistoryZReport='Codecs/LPX/research/tiny-v9-synthesis-history-z-2026-11-16/';
const preparedAttenuationReport='Codecs/LPX/research/tiny-v9-prepared-attenuation-2026-11-16/';
const alignedPitchPageReport='Codecs/LPX/research/tiny-v9-aligned-pitch-page-2026-11-16/';
const lpcZeroSeedReport='Codecs/LPX/research/tiny-v9-lpc-zero-seed-2026-11-16/';
const lpcOddPhaseReport='Codecs/LPX/research/tiny-v9-lpc-odd-phase-2026-11-16/';
const sharedAvrPlayerReport='Codecs/LPX/research/shared-avr-v9-player-2026-11-16/';
const avr5PitchPageReport='Codecs/LPX/research/avr5-v9-pitch-page-2026-11-16/';
const avr5LpcBiasReport='Codecs/LPX/research/avr5-v9-lpc-bias-2026-11-16/';
const avr5Poly24Report='Codecs/LPX/research/avr5-v9-poly24-2026-11-16/';
const avrLsfProductReport='Codecs/LPX/research/avr-v9-lsf-product-2026-11-16/';
const avrIrqRegisterMapReport='Codecs/LPX/research/avr-v9-irq-register-map-2026-11-16/';
const tinyPulseRegistersReport='Codecs/LPX/research/tiny-v9-pulse-registers-2026-11-16/';
const tinyHeaderShortcutsReport='Codecs/LPX/research/tiny-v9-header-shortcuts-2026-11-16/';
const avrPwm130Report='Codecs/LPX/research/avr-v9-pwm130-2026-11-16/';

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
  if(recorded!==actual){
    const rebuild=JSON.parse(read(webuiRebuildReceipt));
    const change=rebuild.sources[path] ?? rebuild.validation_sources[path];
    if(change?.baseline[field]===recorded){
      assert.equal(rebuild.complete,true);
      assert.equal(rebuild.baseline_revision,'3ff5dc0f43db10f0c19a11283694d69bd11e211d');
      assert.equal(rebuild.universal_irq_cases,22);
      assert.equal(rebuild.identical_web_images,18);
      recorded=change.current[field];
    }
  }
  for(const [directory,baseline] of [
    [pulsePacketReport,'1fe7048d7b29e0eb8c76700c4917a3d6f5d57bca'],
    [flashReadReport,'bd3ec1ce42b430dbb2663ddf3ff73996dbb57383'],
    [boundedPwmReport,'31d8aa578098ae3d597735420b2db6c30cd25cf6'],
    [unsignedInterpReport,'62cbe8834061d270bddcd4c6042f1f3f08c69e7d'],
    [staticRomReport,'424d611147f0e96547913b5aa73db55b7c17521c'],
    [romHeaderReport,'cef91038b7d98478ff1c5b14d9b3b0a22bc17f4b'],
    [polySeedReport,'b0ac206459cadf39ed8a9beb6eaae5bb3282f88c'],
    [p4AmplitudeReport,'e13909a07dc475b18e32a37bfc39ff60f77f56f8'],
    [pulseSentinelReport,'e1583321d2186ca3c198d949097a4ebdcda9420b'],
    [lsfInvariantsReport,'85972e200de63745ee77cec6be0081ba7db53be1'],
    [cosEdgeReport,'833a2ad05cc18b77160b1c773a90e5a2cf3af28b'],
    [q4ScaleRuntimeReport,'0f746634fb1b61690bfab0d5c64a8219d291015d'],
    [lpcSaturationReport,'bd8121a5987a670e11426b73abff9a5db213b93e'],
    [q4SynthesisClipReport,'13041e26223245b19eed9b3443f4e56c9a5da058'],
    [joinedBitfieldReport,'881d40b62bb46f09a41fc78688e36647a2aac69a'],
    [oneShotBssReport,'970616ecd82805ee6bc16f620c0b3ead46f561b6'],
    [seededPolyQ8Report,'667360f57425cb9d1045df7ee293624a39ece6d0'],
    [signed6ExcitationReport,'8a1a0310fda1165a2d083bbd2f820904f34c1041'],
    [synthesisHistoryZReport,'f37f1b818669a0335c50a411e03e9760011052fe'],
    [preparedAttenuationReport,'3fc608349445f69e9ed054772010232b614509a9'],
    [alignedPitchPageReport,'cf013a74d477564d106a8e4f25de0061b8b8a812'],
    [lpcZeroSeedReport,'ce0b1c93cee257e2e2899bb9502d67f2b0bce899'],
    [lpcOddPhaseReport,'b5f59cfc1cec5a1d55fafd709a6f2b655d40985a'],
    [sharedAvrPlayerReport,'2e141dcc17f3620042fdfba3610349651921cd18'],
    [avr5PitchPageReport,'799f7b5764e4d4eef88a3475e4354e77158bb7a3'],
    [avr5LpcBiasReport,'95bc776c7fc823601c298a23236a0ab14269d849'],
    [avr5Poly24Report,'b0ea2e27aff3b4807a22ab730bdcc535ef8881ab'],
    [avrLsfProductReport,'98be1f43cb282a7ff0e5a362a22f1f5138b9926d'],
    [avrIrqRegisterMapReport,'fe76b6f2cdea4f023f4d046c7af1138419a89b38'],
    [tinyPulseRegistersReport,'c8a24c9a1203e73cc5aa936cbdb9e4bc9d598214'],
    [tinyHeaderShortcutsReport,'67e41ea9da0cf31764ff7d311e78c2e9c458ff16'],
    [avrPwm130Report,'6037f1527f0df94932b90236796c9c0ff4c18bc6'],
  ]){
    if(recorded===actual)break;
    const report=JSON.parse(read(directory+'source-transition.json'));
    const change=report.sources[path] ?? report.validation_sources?.[path];
    if(change?.baseline[field]===recorded){
      assert.equal(report.baseline_revision,baseline);
      assert.equal(report.complete,true);
      assert.equal(report.universal_irq_cases,22);
      assert.equal(report.identical_web_images,18);
      const evidence=read(directory+'measurements.json');
      assert.equal(sha(evidence.toString('utf8').replaceAll('\r\n','\n')),report.measurements_sha256);
      recorded=change.current[field];
    }
  }
  assert.equal(recorded,actual,path+' current source');
}
