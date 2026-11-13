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
    assert recorded==actual,(path,'current source')
