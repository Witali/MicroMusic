"""Audit retained NB11/WB12.8 admission; optionally rebuild all eight decoders.

This checks source/report/binary provenance, not a fresh PWM simulation. The
retained PWM evidence executes timers and interrupts; no board test is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
import build,build_wb

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def text_digest(p):return hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
def read(name):return json.loads((ROOT/'reports'/name).read_text(encoding='utf-8'))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--avr-gcc',help='Also rebuild eight C/ASM/feature combinations');args=p.parse_args()
    admission=read('higher-admission.json')
    assert admission['textHashNormalization']=='CRLF to LF; firmware images remain raw bytes'
    for name,sha in admission['sourceSha256'].items():assert text_digest(ROOT/name)==sha,name
    for name,sha in admission['reportSha256'].items():assert text_digest(ROOT/'reports'/name)==sha,name
    assert all(read('higher-minimal-identity.json').values())
    assert len(read('higher-legacy-player-identity.json'))==6
    assert all(row['byteIdentical'] for row in read('higher-legacy-player-identity.json'))
    fields=read('higher-fields-unit.json');assert fields['cases']==304192 and fields['exactSevenInputBytesOnce']
    fused=read('higher-fold-unit.json');assert fused['cases']==63360 and fused['selectedAndForcedCExact']
    native=read('higher-native.json');assert sum(r['frames'] for r in native['higherStreams'])==22150
    assert len(native['mixedStreams'])==4 and all(r['invalidCallsBeforeEveryFrame'] and r['resetReplayExact'] for r in native['mixedStreams'])
    for backend in ['asm','c']:
        nb=read('higher-nb-'+backend+'.json');wb=read('higher-wb-'+backend+'.json')
        assert nb['frames']==11587 and wb['frames']==10563
        assert all(r['resetVerified'] for r in nb['streams'])
        assert all(r['reset'] and r['pcmExact'] for r in wb['streams'])
    natural=read('higher-wb-pwm-natural.json');loaded=read('higher-wb-pwm-load5.json')
    assert natural['frames']==6467 and len(natural['streams'])==48 and natural['includesInterrupts']
    assert loaded['frames']==384 and loaded['extraCpuCyclesPerFrame']==16000
    for report in [natural,loaded,read('higher-nb-pwm-normal.json'),read('higher-nb-pwm-load40.json')]:
        assert report['includesInterrupts'] and not report['physicalBoardTested']
        for row in report['streams']:assert row['passed'] and row['underruns']==0 and row['freeSramAtPeak']>0
    package=read('higher-portable.json')
    assert package['testedStaticArchives']==2 and package['higherProfiles']['frames']==22150
    assert package['higherProfiles']['mixedModeAndRejectionChecks']
    minimum=read('higher-portable-minimal.json')
    assert minimum['testedStaticArchives']==2 and 'higherProfiles' not in minimum
    if args.avr_gcc:
        for row in admission['decoderImages']:
            if row['family']=='nb':
                build.avr(args.avr_gcc,backend=row['backend'],packet_bytes=row['packetBytes'])
                image=ROOT/'build/profile/speex-test.bin'
            else:
                out=build_wb.avr(args.avr_gcc,row['backend'],packet_bytes=row['packetBytes'],destination=ROOT/'build/higher-audit-rebuild')
                image=out/'wb.bin'
            assert digest(image)==row['sha256'],row
    print('PASS: higher-profile sources, exact PCM, C export/CMake, mixed modes, IRQ/PWM admission'+('; eight decoder rebuilds identical' if args.avr_gcc else ''))
if __name__=='__main__':main()
