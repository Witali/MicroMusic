#!/usr/bin/env python3
"""Bind WB admission reports to sources, exact binaries, inputs and PWM data.

--rebuild compiles final sources into new directories and requires byte equality
with every executed image. This avoids repeating simulation for comment/EOF
cleanup while preserving the original frozen images and execution reports.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build
import build_wb
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc');p.add_argument('--rebuild',action='store_true')
    args=p.parse_args()
    if args.rebuild and not args.avr_gcc:p.error('--rebuild requires --avr-gcc')
    build.verify_sources()
    native=read(ROOT/'reports/wb1-native.json');by_name={r['stream']:r for r in native['streams']}
    assert native['frames']==10563 and len(by_name)==17
    for name,row in by_name.items():
        assert digest(ROOT/'build/wb-corpus/streams'/name)==row['inputSha256']
        assert digest(ROOT/'build/wb-corpus/oracle'/(Path(name).stem+'.pcm'))==row['pcmSha256']
    images=[]
    for backend in ['asm','c']:
        report=read(ROOT/'reports'/('wb1-'+backend+'.json'))
        image=ROOT/'build'/('wb-'+backend+'-decoder')
        assert report['frames']==10563 and report['binarySha256']==digest(image/'wb.bin')
        assert {r['name']:r['frames'] for r in report['streams']}=={n:r['frames'] for n,r in by_name.items()}
        if args.rebuild:
            fresh=ROOT/'build/wb-final-rebuild'/('decoder-'+backend)
            build_wb.avr(args.avr_gcc,backend,destination=fresh)
            assert digest(fresh/'wb.bin')==report['binarySha256']
        images.append(dict(image='decoder-'+backend,sha256=report['binarySha256'],frames=report['frames']))
    for matrix in ['wb-pwm','wb-pwm-load2']:
        report=read(ROOT/'build'/matrix/'player-all.json')
        assert report['underruns']==0 and report['includesInterrupts'] and report['sampleRate']==16000
        for row in report['streams']:
            candidates=[(n,r) for n,r in by_name.items() if r['inputSha256']==row['input']['sha256']]
            assert len(candidates)==1
            name,source=candidates[0];image=ROOT/'build'/matrix/Path(name).stem
            assert row['binarySha256']==digest(image/'wb.bin')
            oracle=(ROOT/'build/wb-corpus/oracle'/(Path(name).stem+'.pcm')).read_bytes()
            expected=bytes(v^128 for v in oracle[1::2]);pwm=(image/'player-pwm.u8').read_bytes()
            assert expected==pwm and hashlib.sha256(pwm).hexdigest()==row['pwmSha256']
            assert row['frames']==source['frames'] and row['samples']==len(expected)
            assert row['staticSramBytes']+row['peakStackBytes']+row['freeSramAtPeak']==2048
            if args.rebuild:
                fresh=ROOT/'build/wb-final-rebuild'/matrix/Path(name).stem
                build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams'/name,
                    report['extraCpuCyclesPerFrame'],fresh)
                assert digest(fresh/'wb.bin')==row['binarySha256']
            images.append(dict(image=matrix+'/'+Path(name).stem,sha256=row['binarySha256'],frames=row['frames'],pwmExact=True))
            print('BOUND',images[-1]['image'],flush=True)
    portable=read(ROOT/'reports/wb1-portable.json')
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    assert portable['wideband']['streams']==[dict(stream=n,frames=r['frames'],pcmSha256=r['pcmSha256']) for n,r in sorted(by_name.items())]
    unit=read(ROOT/'reports/wb1-kernels.json');assert len(unit['streams'])==6
    for row in unit['streams']:assert row['pcmExact'] and row['guards'] and row['readOnlyInputs']
    nb_expected=dict(asm='fe3f4c24d682009d663bee6929bc5903fb660f1d39a578ab98067ea202c0de63',
        c='46a3f066f72a32de1496f9969bc27c8f182d83abacb4c4b275cfd3f9bce55faa')
    if args.rebuild:
        for backend,expected in nb_expected.items():
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==expected
    paths=list((ROOT/'src').glob('*'))+[ROOT/'tools'/n for n in ['build.py','apply_profile.py','build_wb.py','compare_wb.py']]
    paths+=list((ROOT/'tests').glob('*wb*'))+[ROOT/'tests'/n for n in ['avr_tick.mjs','verify_avr_tick.mjs','verify_portable.py','verify_backend_selection.py']]
    hashes={f.relative_to(ROOT).as_posix():digest(f) for f in sorted(set(paths)) if f.is_file()}
    report=dict(profile='WB1-Q7-16',physicalBoardTested=False,images=images,
        allImagesRebuiltByteIdenticalToExecuted=bool(args.rebuild),sourceSha256=hashes,
        nbOnlyBinaryUnchanged=nb_expected,decoderFramesPerBackend=10563,
        fullPwmFrames=6467,fullPwmSamples=2069440,loadedPwmFrames=808,
        additionalCpuCyclesPerLoadedFrame=6400,underruns=0,
        scope='Exact compact-profile PCM; final QMF intentionally differs from full Xiph synthesis')
    (ROOT/'reports/wb1-admission-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS:',len(images),'bound images; final sources and original vendor hashes verified',flush=True)
if __name__=='__main__':main()
