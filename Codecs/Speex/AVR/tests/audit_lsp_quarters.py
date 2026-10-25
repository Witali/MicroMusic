#!/usr/bin/env python3
"""Bind NB quarter-step measurements to original PCM, frozen sources and images."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
import build
import build_wb
from verify_nb_players import source_hashes as nb_hashes
from verify_wb_players import source_hashes as wb_hashes

def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def mean(rows):return sum(r['frames']*r['meanCycles'] for r in rows)/sum(r['frames'] for r in rows)
def original(name):
    return subprocess.check_output(['git','show','0449cd9:Codecs/Speex/AVR/src/'+name],cwd=ROOT)
def canonical(data):return data.replace(b'\r\n',b'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild',action='store_true')
    parser.add_argument('--avr-gcc')
    args=parser.parse_args()
    if args.rebuild and not args.avr_gcc:parser.error('--rebuild requires --avr-gcc')
    build.verify_sources()
    old_names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',
        '0449cd9:Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {p.name for p in (ROOT/'src').iterdir() if p.is_file()}==old_names|{'nb3_interpolate.h'}
    # Git normalizes these text files; frozen build/source hashes below still
    # compare exact bytes, including each checkout's line endings.
    for name in old_names-{'nb_decode.c.inc'}:assert canonical(original(name))==canonical((ROOT/'src'/name).read_bytes()),name
    assert canonical(original('nb_decode.c.inc'))!=canonical((ROOT/'src/nb_decode.c.inc').read_bytes())
    reports=ROOT/'reports';kept={};images=[];measurements={}
    def retain(name,path):
        data=read(path);shutil.copyfile(path,reports/('lsp-quarter-'+name+'.json'))
        kept[name]=data;return data
    unit=retain('unit',ROOT/'build/quarter-unit/verification.json')
    assert unit['calls']==82688 and unit['exactAgainstUntouchedXiphOnAvr']
    for key in ['rawQuarterStateExact','finalRawEndpointExact','guardsIntact',
                'deltaAndEndpointsPreserved','zeroRegisterRestored']:assert unit[key]
    assert unit['binarySha256']==digest(ROOT/'build/quarter-unit/quarter.bin')
    native_log=(ROOT/'build/quarter-primitives.log').read_text()
    assert '589888 quarter-interpolation cases / 1573120 calls' in native_log
    assert '240000 complete upstream LSP conversions' in native_log
    assert '2000000 direct/transposed LPC samples' in native_log
    native=dict(compiler='Clang 24; -O2 -fwrapv -fno-strict-aliasing',
        quarterCases=589888,quarterCalls=1573120,all262144CodebookTriples=True,
        signedRandomTransitions=65536,edgeTransitions=64,exactAgainstUntouchedXiph=True,
        primitiveBinarySha256=digest(ROOT/'build/profile/primitives.exe'),
        logSha256=digest(ROOT/'build/quarter-primitives.log'),
        sourceSha256={name:digest(ROOT/name) for name in
            ['src/nb3_interpolate.h','tests/primitives.c']},
        passed=[s for s in native_log.splitlines() if s.startswith('PASS')])
    (reports/'lsp-quarter-primitives.json').write_text(json.dumps(native,indent=2)+'\n')
    portable=retain('portable',ROOT/'build/lsp-quarter-portable.json')
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    selection=retain('backend-selection',ROOT/'build/lsp-quarter-backend.json')
    assert len(selection['cases'])==23
    manifest=read(ROOT/'build/cache3-corpus/manifest.json')
    assert manifest['frames']==9100 and len(manifest['streams'])==31
    for row in manifest['streams']:
        assert digest(ROOT/'build/cache3-corpus/streams'/row['stream'])==row['inputSha256']
        assert digest(ROOT/'build/cache3-corpus/oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    wb_manifest=read(reports/'iir-cache3-fresh-wb-oracle.json')
    for row in wb_manifest['streams']:
        assert digest(ROOT/'build/wb-corpus/streams'/row['stream'])==row['inputSha256']
        assert digest(ROOT/'build/wb-corpus/oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    for backend in ['asm','c']:
        full=retain('nb-'+backend,ROOT/('build/lsp-quarter-nb-'+backend+'/avr-verification.json'))
        assert full['frames']==9100 and full['backend']==backend
        assert full['binarySha256']==digest(ROOT/('build/lsp-quarter-nb-'+backend+'/speex-test.bin'))
        before=(read(reports/'iir-cache3-nb-corpus.json')['streams'] if backend=='asm' else
            sum([read(reports/('shared-routines-c-'+n+'.json'))['streams'] for n in ['fixtures','speech']],[]))
        old={r['stream']:r for r in before}
        assert set(old)=={r['stream'] for r in full['streams']}
        for row in full['streams']:
            previous=old[row['stream']]
            assert row['frames']==previous['frames'] and row['resetVerified']
            assert (row['lspConversions'],row['lspCacheHits'])==(previous['lspConversions'],previous['lspCacheHits'])
            assert row['meanCycles']<previous['meanCycles'] and row['maxCycles']<previous['maxCycles']
        frames=full['frames']
        for name,count in [('pitch',4096),('zero',1024),('lsp',58)]:
            extra=retain('nb-'+backend+'-'+name,ROOT/('build/lsp-quarter-nb-'+backend+'-'+name+'/avr-verification.json'))
            assert extra['frames']==count and extra['binarySha256']==full['binarySha256']
            assert all(r['resetVerified'] for r in extra['streams']);frames+=extra['frames']
        assert frames==14278
        measurements['nb-'+backend]=dict(frames=frames,beforeMeanCycles=mean(before),
            afterMeanCycles=mean(full['streams']),meanCyclesSavedPercent=100*(1-mean(full['streams'])/mean(before)),
            beforeMaxCycles=max(r['maxCycles'] for r in before),afterMaxCycles=full['maxCycles'],
            flashBytes=full['flashBytes'],staticSramBytes=full['staticSramBytes'],
            peakStackBytes=2303-full['minStackPointer'],freeSramAtPeak=full['minStackPointer']-256-full['staticSramBytes']+1)
        wb=retain('wb-'+backend,ROOT/('build/lsp-quarter-wb-'+backend+'/verification.json'))
        assert wb['frames']==10563 and wb['backend']==backend
        assert wb['binarySha256']==digest(ROOT/('build/lsp-quarter-wb-'+backend+'/wb.bin'))
        assert all(r['pcmExact'] and r['reset'] for r in wb['streams'])
        repeat=retain('wb-'+backend+'-repeats',ROOT/('build/lsp-quarter-wb-'+backend+'-repeats/verification.json'))
        assert repeat['frames']==744 and repeat['binarySha256']==wb['binarySha256']
        measurements['wb-'+backend]={k:v for k,v in wb.items() if k!='streams'}
    native_repeats=retain('wb-repeats-native',ROOT/'build/lsp-quarter-wb-repeats-native/verification.json')
    assert native_repeats['streams']==read(reports/'iir-cache3-wb-repeats-native.json')['streams']
    for row in native_repeats['streams']:
        folder=ROOT/'build/lsp-quarter-wb-repeats-native'
        packet=folder/('streams/' if row['name']=='repeat_lsp_avr' else '')/(row['name']+'.spxraw')
        assert digest(packet)==row['inputSha256']
        assert digest(folder/'oracle'/(row['name']+'.pcm'))==row['pcmSha256']
    for family,mode,frames,load in [('nb','asm-normal',9100,0),('nb','asm-load40',9100,128000),
        ('nb','c-normal',9100,0),('nb','c-load10',9100,32000),('wb','normal',6467,0),('wb','load5',808,16000)]:
        folder=ROOT/('build/lsp-quarter-'+family+'-'+mode)
        assert read(folder/'source-sha256.json')==(nb_hashes() if family=='nb' else wb_hashes())
        matrix=retain(family+'-'+mode,folder/'player-all.json')
        assert matrix['frames']==frames and matrix['includesInterrupts'] and matrix['underruns']==0
        assert matrix['extraCpuCyclesPerFrame']==load
        for row in matrix['streams']:
            name=Path(row['input']['file']);image=folder/name.stem
            binary=image/('speex-player.bin' if family=='nb' else 'wb.bin')
            corpus=ROOT/'build'/('cache3-corpus' if family=='nb' else 'wb-corpus')
            assert digest(corpus/'streams'/name)==row['input']['sha256']
            assert digest(binary)==row['binarySha256']
            expected=bytes(b^128 for b in (corpus/'oracle'/(name.stem+'.pcm')).read_bytes()[1::2])
            assert (image/'player-pwm.u8').read_bytes()==expected
            assert hashlib.sha256(expected).hexdigest()==row['pwmSha256']
            assert row['staticSramBytes']+row['peakStackBytes']+row['freeSramAtPeak']==2048
            assert row['underruns']==0 and row['minQueuedSamplesBeforeOutput']>0
            if load:assert row['measuredExtraLoadCount']==row['frames']
            images.append(dict(image=binary.relative_to(ROOT).as_posix(),sha256=row['binarySha256']))
    assert len(images)==142
    rebuilt=[]
    if args.rebuild:
        out=ROOT/'build/lsp-quarter-rebuild';out.mkdir(exist_ok=True)
        build.run([sys.executable,ROOT/'tools/build_interpolate_test.py','--avr-gcc',args.avr_gcc])
        assert digest(ROOT/'build/quarter-unit/quarter.bin')==unit['binarySha256']
        for backend in ['asm','c']:
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==kept['nb-'+backend]['binarySha256']
            wb=build_wb.avr(args.avr_gcc,backend,destination=out/('wb-'+backend))
            assert digest(wb/'wb.bin')==kept['wb-'+backend]['binarySha256']
            for load in [0,128000 if backend=='asm' else 32000]:
                build.avr(args.avr_gcc,ROOT/'build/cache3-corpus/streams/speech_ru.spxraw',load,backend)
                mode='normal' if not load else 'load40' if backend=='asm' else 'load10'
                expected=ROOT/('build/lsp-quarter-nb-'+backend+'-'+mode+'/speech_ru/speex-player.bin')
                assert digest(ROOT/'build/player/speex-player.bin')==digest(expected)
                rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
        for mode,load in [('normal',0),('load5',16000)]:
            image=build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams/ru_pushkin_a.spxraw',load,out/('wb-'+mode))
            expected=ROOT/('build/lsp-quarter-wb-'+mode+'/ru_pushkin_a/wb.bin')
            assert digest(image/'wb.bin')==digest(expected)
            rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
    result=dict(scope='Pinned NB3 and compact WB; ATmega328P ISA/peripheral simulation',
        baselineGitCommit='0449cd9',measurements=measurements,frozenPlayerImages=images,
        representativePlayersRebuilt=rebuilt,bothDecoderBackendsRebuilt=args.rebuild,
        nbSourceSha256=nb_hashes(),wbSourceSha256=wb_hashes(),
        unitSourceSha256={name:digest(ROOT/name) for name in ['tests/avr_interpolate.c',
            'tools/build_interpolate_test.py','src/nb3_interpolate.h','vendor/speex-1.2.1/libspeex/lsp.c']},
        physicalBoardTested=False)
    replay=ROOT/'build/lsp-quarter-replay/build/profile/speex-test.bin'
    assert digest(replay)==kept['nb-asm']['binarySha256']
    result['selectedCandidateReproducedSha256']=digest(replay)
    (reports/'lsp-quarter-admission.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: 142 frozen player images; exact NB/WB PCM; both backend source/binary bindings')

if __name__=='__main__':main()
