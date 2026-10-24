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
sys.path.insert(0,str(ROOT/'tests'))
import build
import build_wb
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--avr-gcc');p.add_argument('--rebuild',action='store_true')
    p.add_argument('--speed',action='store_true',help='Audit the subsequent WB speed optimization reports/images')
    p.add_argument('--round2',action='store_true',help='Audit fused excitation and QMF alignment optimization')
    args=p.parse_args()
    if args.rebuild and not args.avr_gcc:p.error('--rebuild requires --avr-gcc')
    if args.speed and args.round2:p.error('Choose one optimization series')
    build.verify_sources()
    optimized=args.speed or args.round2
    prefix='wb2' if args.round2 else 'wb1-speed' if args.speed else 'wb1'
    image_prefix='wb2' if args.round2 else 'wb-speed' if args.speed else 'wb'
    rebuild_root=ROOT/'build'/('wb2-rebuild' if args.round2 else 'wb-speed-rebuild' if args.speed else 'wb-final-rebuild')
    native=read(ROOT/'reports'/(prefix+'-native.json'));by_name={r['stream']:r for r in native['streams']}
    assert native['frames']==10563 and len(by_name)==17
    for name,row in by_name.items():
        assert digest(ROOT/'build/wb-corpus/streams'/name)==row['inputSha256']
        assert digest(ROOT/'build/wb-corpus/oracle'/(Path(name).stem+'.pcm'))==row['pcmSha256']
    images=[]
    for backend in ['asm','c']:
        report=read(ROOT/'reports'/(prefix+'-'+backend+'.json'))
        image=ROOT/'build'/(image_prefix+'-'+backend+'-decoder')
        assert report['frames']==10563 and report['binarySha256']==digest(image/'wb.bin')
        assert {r['name']:r['frames'] for r in report['streams']}=={n:r['frames'] for n,r in by_name.items()}
        assert all(r['pcmExact'] and r['reset'] for r in report['streams'])
        if backend=='c':assert 'speex_wb_excitation40_avr' not in (image/'symbols.txt').read_text()
        if args.rebuild:
            fresh=rebuild_root/('decoder-'+backend)
            build_wb.avr(args.avr_gcc,backend,destination=fresh)
            assert digest(fresh/'wb.bin')==report['binarySha256']
        images.append(dict(image='decoder-'+backend,sha256=report['binarySha256'],frames=report['frames']))
    matrices=[image_prefix+'-pwm',image_prefix+('-pwm-load5' if optimized else '-pwm-load2')]
    for matrix in matrices:
        report=read(ROOT/'build'/matrix/'player-all.json')
        assert report['underruns']==0 and report['includesInterrupts'] and report['sampleRate']==16000
        if optimized:
            from verify_wb_players import source_hashes
            assert read(ROOT/'build'/matrix/'source-sha256.json')==source_hashes()
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
                fresh=rebuild_root/matrix/Path(name).stem
                build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams'/name,
                    report['extraCpuCyclesPerFrame'],fresh)
                assert digest(fresh/'wb.bin')==row['binarySha256']
            images.append(dict(image=matrix+'/'+Path(name).stem,sha256=row['binarySha256'],frames=row['frames'],pwmExact=True))
            print('BOUND',images[-1]['image'],flush=True)
    portable=read(ROOT/'reports'/(prefix+'-portable.json'))
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    assert portable['wideband']['streams']==[dict(stream=n,frames=r['frames'],pcmSha256=r['pcmSha256']) for n,r in sorted(by_name.items())]
    unit=read(ROOT/'reports'/(prefix+'-kernels.json'));assert len(unit['streams'])==(8 if args.round2 else 6)
    for row in unit['streams']:assert row['pcmExact'] and row['guards'] and row['readOnlyInputs']
    if optimized:
        repeats=read(ROOT/'reports'/(prefix+'-repeats-native.json'))
        assert repeats['codebookPairs']==4096 and repeats['streams'][0]['frames']==12288
        for row in repeats['streams']:
            source=ROOT/'build/wb-speed-repeats'
            if row['name']=='repeat_lsp_avr':source=source/'streams'
            assert digest(source/(row['name']+'.spxraw'))==row['inputSha256']
            assert digest(ROOT/'build/wb-speed-repeats/oracle'/(row['name']+'.pcm'))==row['pcmSha256']
        for backend in ['asm','c']:
            repeat=read(ROOT/'reports'/(prefix+'-repeats-'+backend+'.json'))
            full=read(ROOT/'reports'/(prefix+'-'+backend+'.json'))
            assert repeat['frames']==744 and repeat['binarySha256']==full['binarySha256']
            assert all(r['pcmExact'] and r['reset'] for r in repeat['streams'])
    nb_expected=dict(asm='fe3f4c24d682009d663bee6929bc5903fb660f1d39a578ab98067ea202c0de63',
        c='46a3f066f72a32de1496f9969bc27c8f182d83abacb4c4b275cfd3f9bce55faa')
    if args.rebuild:
        for backend,expected in nb_expected.items():
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==expected
    paths=list((ROOT/'src').glob('*'))+[ROOT/'tools'/n for n in ['build.py','apply_profile.py','build_wb.py','compare_wb.py']]
    paths+=list((ROOT/'tests').glob('*wb*'))+[ROOT/'tests'/n for n in ['avr_tick.mjs','verify_avr_tick.mjs','verify_portable.py','verify_backend_selection.py']]
    hashes={f.relative_to(ROOT).as_posix():digest(f) for f in sorted(set(paths)) if f.is_file()}
    loaded=read(ROOT/'build'/matrices[1]/'player-all.json')
    report=dict(profile='WB1-Q7-16',physicalBoardTested=False,images=images,
        allImagesRebuiltByteIdenticalToExecuted=bool(args.rebuild),sourceSha256=hashes,
        nbOnlyBinaryUnchanged=nb_expected,decoderFramesPerBackend=10563,
        fullPwmFrames=6467,fullPwmSamples=2069440,loadedPwmFrames=loaded['frames'],
        additionalCpuCyclesPerLoadedFrame=loaded['extraCpuCyclesPerFrame'],underruns=0,
        scope='Exact compact-profile PCM; final QMF intentionally differs from full Xiph synthesis')
    if optimized:
        before=read(ROOT/'reports'/('wb1-speed-asm.json' if args.round2 else 'wb1-asm.json'))
        after=read(ROOT/'reports'/(prefix+'-asm.json'))
        keys=['binarySha256','frames','flashBytes','staticSramBytes','maxCycles',
              'meanCycles','peakStack','freeSram']
        report['decoderComparison']=dict(before={k:before[k] for k in keys},
            after={k:after[k] for k in keys},
            meanCyclesSavedPercent=100*(1-after['meanCycles']/before['meanCycles']),
            maxCyclesSavedPercent=100*(1-after['maxCycles']/before['maxCycles']))
    (ROOT/'reports'/(prefix+'-admission-audit.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS:',len(images),'bound images; final sources and original vendor hashes verified',flush=True)
if __name__=='__main__':main()
