"""Bind historical timing records without relabelling them as new measurements."""
import hashlib
import json
from pathlib import Path

ACTIVE=Path(__file__).resolve().parents[1]
REPO=ACTIVE.parents[2]
TRANSITION=ACTIVE/'examples/ATTINY88_V5_PLAYER/c-numeric-transition.json'
POLYNOMIAL=REPO/'Codecs/LPX/research/lsf-compact-2026-11-10/source-transition.json'
INTERPOLATION=REPO/'Codecs/LPX/research/lpc-interpolation-2026-11-13/source-transition.json'
SPECTRUM=REPO/'Codecs/LPX/research/tiny-spectrum-anchors-2026-11-13'
PARSER=REPO/'Codecs/LPX/research/tiny-parser-2026-11-13'
LPC_PAIRS=REPO/'Codecs/LPX/research/tiny-lpc-pairs-2026-11-13'
LPC_SHORT=REPO/'Codecs/LPX/research/tiny-lpc-short-2026-11-13'
Q14=REPO/'Codecs/LPX/research/tiny-q14-2026-11-13'
LSF_NEIGHBORS=REPO/'Codecs/LPX/research/tiny-lsf-neighbors-2026-11-13'
MEGA_LSF=REPO/'Codecs/LPX/research/mega-lsf-wide-2026-11-13'
TINY_PITCH=REPO/'Codecs/LPX/research/tiny-v9-pulse-pitch-2026-11-13'
TINY_SHARED_PQ=REPO/'Codecs/LPX/research/tiny-v9-shared-pq-2026-11-13'
TINY_SUBFRAME=REPO/'Codecs/LPX/research/tiny-v9-subframe-2026-11-13'
TINY_ODD_PHASE=REPO/'Codecs/LPX/research/tiny-v9-odd-phase-2026-11-13'
TINY_LPC_HALF=REPO/'Codecs/LPX/research/tiny-v9-lpc-half-2026-11-13'
WEBUI_REBUILD=REPO/'Codecs/LPX/research/webui-rebuild-2026-11-14/source-transition.json'
PULSE_PACKET=REPO/'Codecs/LPX/research/tiny-v9-pulse-packet-2026-11-16'
FLASH_READ=REPO/'Codecs/LPX/research/tiny-v9-flash-read-2026-11-16'
BOUNDED_PWM=REPO/'Codecs/LPX/research/tiny-v9-bounded-pwm-2026-11-16'
UNSIGNED_INTERP=REPO/'Codecs/LPX/research/tiny-v9-unsigned-interp-2026-11-16'
STATIC_ROM=REPO/'Codecs/LPX/research/tiny-v9-static-rom-2026-11-16'
ROM_HEADER=REPO/'Codecs/LPX/research/tiny-v9-rom-header-2026-11-16'
POLY_SEED=REPO/'Codecs/LPX/research/tiny-v9-poly-seed-2026-11-16'
P4_AMPLITUDE=REPO/'Codecs/LPX/research/tiny-v9-p4-amplitude-2026-11-16'
PULSE_SENTINEL=REPO/'Codecs/LPX/research/tiny-v9-pulse-sentinel-2026-11-16'
LSF_INVARIANTS=REPO/'Codecs/LPX/research/tiny-v9-lsf-invariants-2026-11-16'
COS_EDGE=REPO/'Codecs/LPX/research/tiny-v9-cos-edge-2026-11-16'
Q4_SCALE_RUNTIME=REPO/'Codecs/LPX/research/tiny-v9-q4-scale-runtime-2026-11-16'
LPC_SATURATION=REPO/'Codecs/LPX/research/tiny-v9-lpc-saturation-2026-11-16'
Q4_SYNTHESIS_CLIP=REPO/'Codecs/LPX/research/tiny-v9-q4-synthesis-clip-2026-11-16'
JOINED_BITFIELD=REPO/'Codecs/LPX/research/tiny-v9-joined-bitfield-2026-11-16'
ONE_SHOT_BSS=REPO/'Codecs/LPX/research/tiny-v9-one-shot-bss-2026-11-16'
SEEDED_POLY_Q8=REPO/'Codecs/LPX/research/tiny-v9-poly-seeded-q8-2026-11-16'
SIGNED6_EXCITATION=REPO/'Codecs/LPX/research/tiny-v9-signed6-excitation-2026-11-16'
SYNTHESIS_HISTORY_Z=REPO/'Codecs/LPX/research/tiny-v9-synthesis-history-z-2026-11-16'
PREPARED_ATTENUATION=REPO/'Codecs/LPX/research/tiny-v9-prepared-attenuation-2026-11-16'
ALIGNED_PITCH_PAGE=REPO/'Codecs/LPX/research/tiny-v9-aligned-pitch-page-2026-11-16'
LPC_ZERO_SEED=REPO/'Codecs/LPX/research/tiny-v9-lpc-zero-seed-2026-11-16'
LPC_ODD_PHASE=REPO/'Codecs/LPX/research/tiny-v9-lpc-odd-phase-2026-11-16'
SHARED_AVR_PLAYER=REPO/'Codecs/LPX/research/shared-avr-v9-player-2026-11-16'
AVR5_PITCH_PAGE=REPO/'Codecs/LPX/research/avr5-v9-pitch-page-2026-11-16'
AVR5_LPC_BIAS=REPO/'Codecs/LPX/research/avr5-v9-lpc-bias-2026-11-16'
AVR5_POLY24=REPO/'Codecs/LPX/research/avr5-v9-poly24-2026-11-16'
AVR_LSF_PRODUCT=REPO/'Codecs/LPX/research/avr-v9-lsf-product-2026-11-16'
AVR_IRQ_REGISTER_MAP=REPO/'Codecs/LPX/research/avr-v9-irq-register-map-2026-11-16'
TINY_PULSE_REGISTERS=REPO/'Codecs/LPX/research/tiny-v9-pulse-registers-2026-11-16'
TINY_HEADER_SHORTCUTS=REPO/'Codecs/LPX/research/tiny-v9-header-shortcuts-2026-11-16'
AVR_PWM130=REPO/'Codecs/LPX/research/avr-v9-pwm130-2026-11-16'


def assert_recorded_source(path,expected):
    actual=hashlib.sha256((REPO/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    if actual==expected:return
    recorded=expected
    numeric=json.loads(TRANSITION.read_text(encoding='utf-8'))
    source=numeric['sources'].get(path)
    if source and source['baseline'] and source['baseline']['text_lf_sha256']==recorded:
        assert numeric['complete'] and numeric['baseline_revision']=='393b2de271568890d7b483f7602a2f59452d1a68'
        assert numeric['asm_equivalence']['all_binaries_exact'] and numeric['asm_equivalence']['images']==18
        recorded=source['current']['text_lf_sha256']
    if recorded!=actual:
        polynomial=json.loads(POLYNOMIAL.read_text(encoding='utf-8'))
        change=polynomial['sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert polynomial['complete'] and polynomial['baseline_revision']=='0320c1014618188a3121fdfef0be55b30690d977'
            assert polynomial['all_measured_no_speed_loss'] and polynomial['all_measured_no_program_growth']
            assert polynomial['all_fixed_native_exact'] and polynomial['float_binary_exact']
            assert polynomial['fresh_universal_tiny_cases']==22 and polynomial['fresh_mega_cases']==8
            assert polynomial['fresh_website_tiny_cases']==9 and polynomial['identical_nano_images']==9
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        interpolation=json.loads(INTERPOLATION.read_text(encoding='utf-8'))
        change=interpolation['sources'].get(path) or interpolation['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert interpolation['complete'] and interpolation['baseline_revision']=='e0939e89d88e4d91e9e441310f504ddbfd5581aa'
            assert interpolation['all_fixed_native_exact'] and interpolation['all_avr_corpus_exact_without_slowdown']
            assert interpolation['identical_asm_images']==44
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        spectrum=json.loads((SPECTRUM/'source-transition.json').read_text(encoding='utf-8'))
        change=spectrum['sources'].get(path) or spectrum['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert spectrum['complete'] and spectrum['baseline_revision']=='de98d64162368cf3b6104907076a7e1c3d3f3f17'
            assert spectrum['universal_irq_cases']==22 and spectrum['identical_fixed_header_images']==9
            evidence=(SPECTRUM/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==spectrum['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    for step in ('read-bits','rice'):
        if recorded==actual:break
        parser=json.loads((PARSER/f'{step}-transition.json').read_text(encoding='utf-8'))
        change=parser['sources'].get(path) or parser['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert parser['complete'] and parser['step']==step
            assert parser['universal_irq_cases']==22 and parser['identical_fixed_header_images']==9
            evidence=(PARSER/f'{step}.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==parser['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    for directory,revision in (
        (LPC_PAIRS,'84de5ce411a1ace1b29a732f0998c10f67f3e53f'),
        (LPC_SHORT,'26faf77221d4259eda9859b545e2ed25b12b898a'),
        (Q14,'dc522dea665e544aebc95b550a7789186e7bec0d'),
        (LSF_NEIGHBORS,'b4a9757364280049ec7cd2504c8fddfff3a56900'),
    ):
        if recorded==actual:break
        report=json.loads((directory/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['baseline_revision']==revision
            assert report['universal_irq_cases']==22 and report['identical_fixed_header_images']==9
            evidence=(directory/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        report=json.loads((MEGA_LSF/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['baseline_revision']=='ddefa0c4ffcc18cf16e659fa0ab3652f1f7dca84'
            assert report['mega_asm_irq_cases']==6 and report['identical_mega_c_images']==4
            assert report['identical_nano_images']==9
            evidence=(MEGA_LSF/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        report=json.loads((TINY_PITCH/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['complete'] and report['baseline_revision']=='65c3073e354b9956d252c7d118e40ddaae19dd83'
            assert report['universal_irq_cases']==22 and report['identical_web_images']==18
            evidence=(TINY_PITCH/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        report=json.loads((TINY_SHARED_PQ/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['complete'] and report['baseline_revision']=='c391ad095b5ca6c79ef27add0471029a33a6c88c'
            assert report['universal_irq_cases']==22 and report['identical_web_images']==18
            evidence=(TINY_SHARED_PQ/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        report=json.loads((TINY_SUBFRAME/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['complete'] and report['baseline_revision']=='9760ff7f76e66ff6325752fd15278e144bbf0598'
            assert report['universal_irq_cases']==22 and report['identical_web_images']==18
            evidence=(TINY_SUBFRAME/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        report=json.loads((TINY_ODD_PHASE/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['complete'] and report['baseline_revision']=='703174249a5dba87cc796174edc2598bcbd24652'
            assert report['universal_irq_cases']==22 and report['identical_web_images']==18
            evidence=(TINY_ODD_PHASE/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        report=json.loads((TINY_LPC_HALF/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report['validation_sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['complete'] and report['baseline_revision']=='c415ab84c5e00a77c36eb10a5c4b6384c172c068'
            assert report['universal_irq_cases']==22 and report['identical_web_images']==18
            evidence=(TINY_LPC_HALF/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        rebuild=json.loads(WEBUI_REBUILD.read_text(encoding='utf-8'))
        change=rebuild['sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert rebuild['complete'] and rebuild['baseline_revision']=='3ff5dc0f43db10f0c19a11283694d69bd11e211d'
            assert rebuild['universal_irq_cases']==22 and rebuild['identical_web_images']==18
            recorded=change['current']['text_lf_sha256']
    for directory,baseline in (
        (PULSE_PACKET,'1fe7048d7b29e0eb8c76700c4917a3d6f5d57bca'),
        (FLASH_READ,'bd3ec1ce42b430dbb2663ddf3ff73996dbb57383'),
        (BOUNDED_PWM,'31d8aa578098ae3d597735420b2db6c30cd25cf6'),
        (UNSIGNED_INTERP,'62cbe8834061d270bddcd4c6042f1f3f08c69e7d'),
        (STATIC_ROM,'424d611147f0e96547913b5aa73db55b7c17521c'),
        (ROM_HEADER,'cef91038b7d98478ff1c5b14d9b3b0a22bc17f4b'),
        (POLY_SEED,'b0ac206459cadf39ed8a9beb6eaae5bb3282f88c'),
        (P4_AMPLITUDE,'e13909a07dc475b18e32a37bfc39ff60f77f56f8'),
        (PULSE_SENTINEL,'e1583321d2186ca3c198d949097a4ebdcda9420b'),
        (LSF_INVARIANTS,'85972e200de63745ee77cec6be0081ba7db53be1'),
        (COS_EDGE,'833a2ad05cc18b77160b1c773a90e5a2cf3af28b'),
        (Q4_SCALE_RUNTIME,'0f746634fb1b61690bfab0d5c64a8219d291015d'),
        (LPC_SATURATION,'bd8121a5987a670e11426b73abff9a5db213b93e'),
        (Q4_SYNTHESIS_CLIP,'13041e26223245b19eed9b3443f4e56c9a5da058'),
        (JOINED_BITFIELD,'881d40b62bb46f09a41fc78688e36647a2aac69a'),
        (ONE_SHOT_BSS,'970616ecd82805ee6bc16f620c0b3ead46f561b6'),
        (SEEDED_POLY_Q8,'667360f57425cb9d1045df7ee293624a39ece6d0'),
        (SIGNED6_EXCITATION,'8a1a0310fda1165a2d083bbd2f820904f34c1041'),
        (SYNTHESIS_HISTORY_Z,'f37f1b818669a0335c50a411e03e9760011052fe'),
        (PREPARED_ATTENUATION,'3fc608349445f69e9ed054772010232b614509a9'),
        (ALIGNED_PITCH_PAGE,'cf013a74d477564d106a8e4f25de0061b8b8a812'),
        (LPC_ZERO_SEED,'ce0b1c93cee257e2e2899bb9502d67f2b0bce899'),
        (LPC_ODD_PHASE,'b5f59cfc1cec5a1d55fafd709a6f2b655d40985a'),
        (SHARED_AVR_PLAYER,'2e141dcc17f3620042fdfba3610349651921cd18'),
        (AVR5_PITCH_PAGE,'799f7b5764e4d4eef88a3475e4354e77158bb7a3'),
        (AVR5_LPC_BIAS,'95bc776c7fc823601c298a23236a0ab14269d849'),
        (AVR5_POLY24,'b0ea2e27aff3b4807a22ab730bdcc535ef8881ab'),
        (AVR_LSF_PRODUCT,'98be1f43cb282a7ff0e5a362a22f1f5138b9926d'),
        (AVR_IRQ_REGISTER_MAP,'fe76b6f2cdea4f023f4d046c7af1138419a89b38'),
        (TINY_PULSE_REGISTERS,'c8a24c9a1203e73cc5aa936cbdb9e4bc9d598214'),
        (TINY_HEADER_SHORTCUTS,'67e41ea9da0cf31764ff7d311e78c2e9c458ff16'),
        (AVR_PWM130,'6037f1527f0df94932b90236796c9c0ff4c18bc6'),
    ):
        if recorded==actual:break
        report=json.loads((directory/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path) or report.get('validation_sources',{}).get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['complete'] and report['baseline_revision']==baseline
            assert report['universal_irq_cases']==22 and report['identical_web_images']==18
            evidence=(directory/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            recorded=change['current']['text_lf_sha256']
    assert recorded==actual,(path,'current source')
