"""Bind historical timing records without relabelling them as new measurements."""
import hashlib
import json
from pathlib import Path

ACTIVE=Path(__file__).resolve().parents[1]
REPO=ACTIVE.parents[2]
TRANSITION=ACTIVE/'examples/ATTINY88_V5_PLAYER/c-numeric-transition.json'


def assert_recorded_source(path,expected):
    actual=hashlib.sha256((REPO/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    if actual==expected:return
    transition=json.loads(TRANSITION.read_text(encoding='utf-8'))
    assert transition['complete'] and transition['baseline_revision']=='393b2de271568890d7b483f7602a2f59452d1a68'
    source=transition['sources'][path]
    assert source['baseline']['text_lf_sha256']==expected,(path,'historical source')
    assert source['current']['text_lf_sha256']==actual,(path,'current source')
    assert transition['asm_equivalence']['all_binaries_exact'] and transition['asm_equivalence']['images']==18
