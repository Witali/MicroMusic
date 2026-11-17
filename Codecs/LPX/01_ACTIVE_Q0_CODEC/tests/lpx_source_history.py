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
AVR_ROM_CURSOR=REPO/'Codecs/LPX/research/avr-v9-rom-cursor-2026-11-16'
AVR_PACKET_READER=REPO/'Codecs/LPX/research/avr-v9-packet-reader-2026-11-16'
AVR_FINAL_PWM_CLIP=REPO/'Codecs/LPX/research/avr-v9-final-pwm-clip-2026-11-16'
AVR5_LPC_TWO_PASSES=REPO/'Codecs/LPX/research/avr5-v9-lpc-two-passes-2026-11-16'
AVR_LSF_ADDRESSING=REPO/'Codecs/LPX/research/avr-v9-lsf-addressing-2026-11-17'
AVR_LSF_FRAME=REPO/'Codecs/LPX/research/avr-v9-lsf-frame-2026-11-17'
AVR_POLY_WIDTH=REPO/'Codecs/LPX/research/avr-v9-poly24-width-2026-11-17'
AVR_SUBFRAME_PHASE=REPO/'Codecs/LPX/research/avr-v9-subframe-phase-2026-11-17'
TINY_FRAME_RICE=REPO/'Codecs/LPX/research/tiny-v9-frame-rice-2026-11-17'
AVR_ROM_START=REPO/'Codecs/LPX/research/avr-v9-rom-start-2026-11-17'
AVR_ROM_REFILL=REPO/'Codecs/LPX/research/avr-v9-rom-refill-2026-11-17'
AVR_PULSE_SWAP=REPO/'Codecs/LPX/research/avr-v9-pulse-swap-2026-11-17'
AVR5_LPC_CIRCULAR=REPO/'Codecs/LPX/research/avr5-v9-lpc-circular-2026-11-17'
AVR_SHARED_SCALE=REPO/'Codecs/LPX/research/avr-v9-shared-scale-2026-11-17'
TINY_LPC_SATURATED=REPO/'Codecs/LPX/research/tiny-v9-lpc-saturated-2026-11-17'
TINY_POLY_SEED=REPO/'Codecs/LPX/research/tiny-v9-poly-seed-2026-11-17'
AVR5_POLY_PAGE=REPO/'Codecs/LPX/research/avr5-v9-poly-page-2026-11-17'
AVR_POLY_IMMEDIATE=REPO/'Codecs/LPX/research/avr-v9-poly-immediate-2026-11-17'
AVR_PLAYER_DRAIN=REPO/'Codecs/LPX/research/avr-v9-player-drain-2026-11-17'
AVR_STATIC_OPEN=REPO/'Codecs/LPX/research/avr-v9-static-open-2026-11-17'
AVR_BIT_READER_Z=REPO/'Codecs/LPX/research/avr-v9-bit-reader-z-2026-11-17'
AVR5_HISTORY_SRAM=REPO/'Codecs/LPX/research/avr5-v9-history-sram-2026-11-17'
AVR_POLY_CLIP_BIT=REPO/'Codecs/LPX/research/avr-v9-poly-clip-bit-2026-11-17'
TINY_ANCHOR_RAM=REPO/'Codecs/LPX/research/tiny-v9-anchor-sram-2026-11-17'
AVR5_P6_MUL=REPO/'Codecs/LPX/research/avr5-v9-p6-mul-2026-11-17'
AVR5_EXCITATION_LEAF=REPO/'Codecs/LPX/research/avr5-v9-excitation-leaf-2026-11-17'
AVR5_LSF_OVERLAY=REPO/'Codecs/LPX/research/avr5-v9-lsf-overlay-2026-11-17'
AVR_PLAYER_SAMPLE_END=REPO/'Codecs/LPX/research/avr-v9-sample-end-2026-11-17'
AVR_MATH_DEFAULT_BUILD=REPO/'Codecs/LPX/research/avr-math-default-build-2026-11-17'
TINY_SMALL_EXCITATION=REPO/'Codecs/LPX/research/tiny-v9-small-excitation-2026-11-17'
TINY_RICE_DERIVED=REPO/'Codecs/LPX/research/tiny-v9-rice-width-2026-11-17'
AVR5_VECTOR_GAIN=REPO/'Codecs/LPX/research/avr5-v9-vector-gain-2026-11-17'
AVR5_DIRECT_Q4=REPO/'Codecs/LPX/research/avr5-v9-direct-q4-2026-11-17'
AVR5_SATURATION_RAILS=REPO/'Codecs/LPX/research/avr5-v9-saturation-rails-2026-11-17'
TINY_PREPARE_REGISTERS=REPO/'Codecs/LPX/research/tiny-v9-prepare-registers-2026-11-17'
AVR5_FMUL_FILTER=REPO/'Codecs/LPX/research/avr5-v9-fmul-filter-2026-11-17'
AVR5_PLAYER_WORDS=REPO/'Codecs/LPX/research/avr5-v9-player-words-2026-11-17'
AVR5_SHARED_FILTER=REPO/'Codecs/LPX/research/avr5-v9-shared-filter-2026-11-17'
TINY_FILTER_PREVIOUS=REPO/'Codecs/LPX/research/tiny-v9-filter-previous-2026-11-17'
AVR_PLAYER_ERROR_ALIAS=REPO/'Codecs/LPX/research/avr-v9-error-alias-2026-11-17'
TINY_PLAYER_REGISTERS=REPO/'Codecs/LPX/research/tiny-v9-player-registers-2026-11-17'
TINY_WORD_SATURATION=REPO/'Codecs/LPX/research/tiny-v9-word-saturation-2026-11-17'
AVR_PLAYER_GPIOR=REPO/'Codecs/LPX/research/avr-v9-gpior-state-2026-11-17'
TINY_CONVERTER_ABI=REPO/'Codecs/LPX/research/tiny-v9-converter-abi-2026-11-17'
TINY_PREPARED_HALF_PHASE=REPO/'Codecs/LPX/research/tiny-v9-prepared-half-phase-2026-11-17'
TINY_FOLD_COUNTDOWN=REPO/'Codecs/LPX/research/tiny-v9-fold-countdown-2026-11-17'
TINY_COSINE_TRIM=REPO/'Codecs/LPX/research/tiny-v9-cosine-trim-2026-11-17'


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
        (AVR_ROM_CURSOR,'58d83da3045b3d958132909aef41c239baa9e333'),
        (AVR_PACKET_READER,'8bd91924b78ae510bc4b04137fe2baf93ec62345'),
        (AVR_FINAL_PWM_CLIP,'971de4b246d2dd2b4e40a1e281c45fd2558b7166'),
        (AVR5_LPC_TWO_PASSES,'26470b553cc5f9392fc5e250da22aca86a2a1e47'),
        (AVR_LSF_ADDRESSING,'c4a988f3f922f4356e91ccc4ae6d1c6ab1f4ee84'),
        (AVR_LSF_FRAME,'95dca671cf1cc7cb7beb7b9085f4d269b0a0a43d'),
        (AVR_POLY_WIDTH,'0eb4f9525e56a59a234c49d64e46632010cf984c'),
        (AVR_SUBFRAME_PHASE,'2389ef364a722fe7793f8a54df24269d52f9527f'),
        (TINY_FRAME_RICE,'9a2f76626b9cb9c9a7f5be5bd81ebd17c4ccf9e0'),
        (AVR_ROM_START,'7c7aa0b2704ed97d5a5a56882048ecfc5c547b8b'),
        (AVR_ROM_REFILL,'d6e878101d37718234a13d7365ece466debc8242'),
        (AVR_PULSE_SWAP,'a8c0015d2a672cadc799b9bc019aafebad082a3c'),
        (AVR5_LPC_CIRCULAR,'4d3d52cb8970c0183242c24be097eb493242a15c'),
        (AVR_SHARED_SCALE,'573aebc0a800aa10b3a99c59bb839c945be1dc94'),
        (TINY_LPC_SATURATED,'0f5ef996f603c6962f8c693b7ec4ea587610b174'),
        (TINY_POLY_SEED,'5f7fd2028ee18acc3e848b5207a0243b1775201b'),
        (AVR5_POLY_PAGE,'2115dcad6ec59e3fc6197f069fce7624884003fd'),
        (AVR_POLY_IMMEDIATE,'78a79936e3070e8fb3b6a9177e32e9ef267cac1a'),
        (AVR_PLAYER_DRAIN,'d3121d64b4c73fb9d76be17982989cd6bfe2fde2'),
        (AVR_STATIC_OPEN,'3d06727f2b4ad1d6a663c670f1b960e1069caccf'),
        (AVR_BIT_READER_Z,'5487faa80b5f697d366cade0977dca471c27142e'),
        (AVR5_HISTORY_SRAM,'371e74373c6a1b521cfd48af353723be9493efda'),
        (AVR_POLY_CLIP_BIT,'57ac2cee74a436a177b203e1894a4eb0f6a728ab'),
        (TINY_ANCHOR_RAM,'bb9c75b261d7254d3548490653c16878ae43c97b'),
        (AVR5_P6_MUL,'e96796871af5a3f49e680c18c08e6fa334b660aa'),
        (AVR5_EXCITATION_LEAF,'f2d665670d2902ea874d3253e94fa1b9e6bc3ce7'),
        (AVR5_LSF_OVERLAY,'f01f5cbc0937cfeffccfba0f1852cea7fc816c6f'),
        (AVR_PLAYER_SAMPLE_END,'78a9d52a48f07ab36283752e88a57e36fbdc65b9'),
        (AVR_MATH_DEFAULT_BUILD,'cdf197ce495b3dcbf9c807b39062987e8360f030'),
        (TINY_SMALL_EXCITATION,'05fdea6c39bdcaa0d6c03e3f783c4a70a4a08036'),
        (TINY_RICE_DERIVED,'0968d30ca1ff711dacccbbabe7960df1984fb8fb'),
        (AVR5_VECTOR_GAIN,'18bda37dae0677a76af742810bbc82677cc1a264'),
        (AVR5_DIRECT_Q4,'e08d60bfe41559c5a1cb67d989f0979f6955e2a5'),
        (AVR5_SATURATION_RAILS,'13f76faf5f35042972ac24f0695bebb50d77adc0'),
        (TINY_PREPARE_REGISTERS,'2e1e4a0471756ae6827256d03f11586a5dd7712b'),
        (AVR5_FMUL_FILTER,'d75d66e355046ac4e1eb7527ebcc685d020cea4b'),
        (AVR5_PLAYER_WORDS,'527dd8a3c42ed69fe7cb3b9d054ca25edc4ce80b'),
        (AVR5_SHARED_FILTER,'fba54e7b6e9458b483cf4b906f8a2c3c1684b5b2'),
        (TINY_FILTER_PREVIOUS,'c2cade24834e23d082ec969c1d10dcac0a6d4839'),
        (AVR_PLAYER_ERROR_ALIAS,'9b73ddd3618280f3ce441fdb4b1d16a45eba44e6'),
        (TINY_PLAYER_REGISTERS,'dd3a5f283c6e0b65c9f3c01d1fbcb1477708c799'),
        (TINY_WORD_SATURATION,'83e247672e1d02ca8c01f8e283706e6042dfe870'),
        (AVR_PLAYER_GPIOR,'aa99d9ec0945ea65dd845e5b39ed11800a801cd6'),
        (TINY_CONVERTER_ABI,'bfcd72e23b922c76481e23447b6866dabb83f359'),
        (TINY_PREPARED_HALF_PHASE,'2d8734097980fa6f8f2ff74918e57241317aae7a'),
        (TINY_FOLD_COUNTDOWN,'8abf10289a06a4f6d5c9e64cdbc1ba3aaa0a368b'),
        (TINY_COSINE_TRIM,'287222483673a568714713f07c352be042cc4707'),
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
    if recorded!=actual:
        directory=REPO/'Codecs/LPX/research/nano-webui-v9-2026-11-17'
        release=json.loads((directory/'source-transition.json').read_text(encoding='utf-8'))
        change=release['sources'].get(path)
        if change and change['baseline'] and change['baseline']['text_lf_sha256']==recorded:
            assert release['schema']=='lpx-nano-webui-v9-transition-v1'
            assert release['baseline_revision']=='717d20aa27d33a1440ea8f30d7764137b0e6311d'
            evidence=(directory/'rebuild.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==release['rebuild_sha256']
            result=json.loads(evidence)
            assert len(result['cases'])==9 and result['unchanged_tiny_images']==9
            assert result['independent_rebuild']['all_binaries_exact']
            assert len(result['independent_rebuild']['cases'])==18
            assert all(row['pwm_exact'] and row['size_reduced'] and row['after']['underruns']==0
                       for row in result['cases'])
            recorded=change['current']['text_lf_sha256']
    # Later player reductions pair complete producers on both supported CPUs.
    # Older WebUI receipts remain historical; they need not describe new HEXes.
    directory=REPO/'Codecs/LPX/research/avr-player-3k-2026-11-17'
    for step in json.loads((directory/'steps.json').read_text(encoding='utf-8')):
        if recorded==actual:break
        report=json.loads((directory/step).read_text(encoding='utf-8'))
        change=report['sources'].get(path)
        if not change or change['baseline']['text_lf_sha256']!=recorded:continue
        assert report['schema']=='lpx-avr-player-step-v1' and report['complete']
        assert report['kind'] in ('reduction','rate-extension')
        evidence=(directory/report['measurements']).read_bytes().replace(b'\r\n',b'\n')
        assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
        rows=json.loads(evidence)['cases']
        assert len(rows)==44
        assert all(sum(r['target']==t for r in rows)==22 for t in ('attiny88','atmega328p'))
        for row in rows:
            before,after=row['before'],row['after']
            assert after['accepted'] and after['underruns']==0
            assert before['pwm_sha256']==after['pwm_sha256']
            assert before['samples']==after['samples']==after['producer_calls']==after['decode_calls']
            assert after['producer_unpublished_decode_calls']==0
            for field in ('producer_cpu_mean','producer_cpu_max','producer_active_cpu_mean','producer_active_cpu_max'):
                assert after[field]+after['irq_max']<=before[field]+before['irq_max']
            for field in ('static_ram_bytes','stack_bytes'):
                assert after[field]<=before[field]
            if report['kind']=='reduction':
                assert after['program_excluding_audio_bytes']<=before['program_excluding_audio_bytes']
            else:
                # Explicit extra feature: bound its measured code cost against
                # the optimized 8 kHz-only control, retaining the Nano cap.
                overhead=40 if row['target']=='atmega328p' else 36
                assert after['program_excluding_audio_bytes']<=row['compatibility_program_bytes']+overhead
                if row['target']=='atmega328p':assert after['program_excluding_audio_bytes']<=3072
        recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        directory=REPO/'Codecs/LPX/research/avr-player-3k-2026-11-17'
        report=json.loads((directory/'web-release-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['schema']=='lpx-avr-player-web-release-v1'
            assert report['baseline_revision']=='f69487c3ae6e14e888717d60edbaa11511285bcf'
            evidence=(directory/'web-rebuild.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            result=json.loads(evidence)
            assert len(result['cases'])==18 and result['all_audio_stream_assets_unchanged']
            assert result['independent_rebuild']['all_binaries_exact']
            assert result['independent_rebuild']['all_no_float_runtime_symbols']
            assert len(result['independent_rebuild']['cases'])==18
            assert all(r['exact_old_new_pwm'] and r['old_elf_matches_published_hex'] and
                       r['producer_and_irq_after']<=r['producer_and_irq_before'] and
                       r['producer_cpu_max_delta']<=0 for r in result['timing_comparison'])
            recorded=change['current']['text_lf_sha256']
    if recorded!=actual:
        directory=REPO/'Codecs/LPX/research/avr-fixed-rate-2026-11-18'
        report=json.loads((directory/'source-transition.json').read_text(encoding='utf-8'))
        change=report['sources'].get(path)
        if change and change['baseline']['text_lf_sha256']==recorded:
            assert report['schema']=='lpx-avr-fixed-rate-transition-v1'
            evidence=(directory/'measurements.json').read_bytes().replace(b'\r\n',b'\n')
            assert hashlib.sha256(evidence).hexdigest()==report['measurements_sha256']
            rows=json.loads(evidence)['cases'];assert len(rows)==132
            for row in rows:
                before=row['before']
                for key in ('input_sha256','pwm_sha256','underruns','static_ram_bytes','stack_bytes',
                            'producer_cpu_mean','producer_cpu_max','producer_active_cpu_mean','producer_active_cpu_max'):
                    assert row[key]==before[key],(row['target'],row['rate'],row['case'],key)
                assert row['program_excluding_audio_bytes']<before['program_excluding_audio_bytes']
                assert row['irq_max']<=before['irq_max']
                if row['rate']==8000 or row['target']=='atmega328p':assert row['accepted']
            recorded=change['current']['text_lf_sha256']
    assert recorded==actual,(path,'current source')
