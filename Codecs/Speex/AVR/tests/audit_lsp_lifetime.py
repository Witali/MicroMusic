#!/usr/bin/env python3
"""Bind LSP lifetime/bounds optimization to original PCM, frozen PWM and rebuilds."""
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

def read(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def mean(rows):return sum(r['frames']*r['meanCycles'] for r in rows)/sum(r['frames'] for r in rows)
def canonical(data):return data.replace(b'\r\n',b'\n')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rebuild',action='store_true');parser.add_argument('--avr-gcc')
    args=parser.parse_args()
    if args.rebuild and not args.avr_gcc:parser.error('--rebuild requires --avr-gcc')
    build.verify_sources()
    base='928d18e';changed={'nb_decode.c.inc','speex_avr.c','nb3_interpolate.h'}
    names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',
        base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {p.name for p in (ROOT/'src').iterdir() if p.is_file()}==names
    for name in names-changed:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert canonical(old)==canonical((ROOT/'src'/name).read_bytes()),name
    reports=ROOT/'reports';kept={};measurements={};images=[];rebuilt=[]
    def retain(name,path):
        data=read(path);shutil.copyfile(path,reports/('lifetime-'+name+'.json'));kept[name]=data;return data
    units={}
    for backend in ['asm','c']:
        unit=retain('unit-'+backend,ROOT/('build/lifetime-unit-'+backend+'/verification.json'));units[backend]=unit
        assert unit['backend']==backend and unit['boundedCases']==12804 and unit['boundedCalls']==49680
        assert unit['lpcInputs']==4096 and unit['overlappingLpcOutputs']==12288 and unit['disjointLpcOutputs']==4096
        assert unit['aliasOffsets']==[-1,0,1] and unit['retChecks']==66064
        for key in ['exactAgainstUntouchedXiphOnAvr','rawQuarterStateExact','deltaAndEndpointsPreserved',
            'memoryOutsideLpcOutputPreserved','oracleArenaGuardsIntact','guardsIntact','calleeSavedRegistersAtRet','zeroRegisterAtRet']:assert unit[key]
        assert digest(ROOT/('build/lifetime-unit-'+backend+'/lifetime.bin'))==unit['binarySha256']
    log=(ROOT/'build/lifetime-unit-c/native.log').read_text()
    assert '589828 bounded cases / 1572880 calls' in log and 'raw range 96..24880' in log
    assert '240000 LPC inputs / 720000 overlapping outputs' in log
    native=dict(boundedCases=589828,boundedCalls=1572880,all262144CodeTriples=True,minRaw=96,maxRaw=24880,
        lpcInputs=240000,overlappingLpcOutputs=720000,aliasOffsets=[-1,0,1],exactAgainstUntouchedXiph=True,
        compiler='Clang 24 -std=c11 -O2 -fwrapv -fno-strict-aliasing; separate non-LTO oracle objects',
        binarySha256=digest(ROOT/'build/lifetime-unit-c/native.exe'),
        sourceSha256={p:digest(ROOT/p) for p in ['src/nb3_interpolate.h','src/compact_lsp.c.inc',
            'tests/lsp_lifetime.c','tools/build_lsp_lifetime_test.py']})
    (reports/'lifetime-native-unit.json').write_text(json.dumps(native,indent=2)+'\n')
    generic=retain('generic-unit',ROOT/'build/lifetime-generic-unit/verification.json')
    assert generic['calls']==82688 and generic['fullSignedMultiples16Transitions']==16384
    for key in ['exactAgainstUntouchedXiphOnAvr','rawQuarterStateExact','guardsIntact','deltaAndEndpointsPreserved']:assert generic[key]
    assert digest(ROOT/'build/lifetime-generic-unit/quarter.bin')==generic['binarySha256']
    primitive_log=(ROOT/'build/lifetime-native.log').read_text()
    assert '240000 complete upstream LSP conversions' in primitive_log and '1573120 calls' in primitive_log
    scratch=retain('native-scratch',ROOT/'build/lifetime-native-scratch/verification.json')
    assert scratch['frames']==9100 and scratch['instrumentedPushChecksEnabled'] and scratch['scratchPeak']==40
    assert scratch['exactPcm'] and len(scratch['streams'])==31
    assert scratch['sourceSha256']=={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'src').iterdir()) if p.is_file()}
    assert digest(ROOT/'build/profile'/('decode.exe' if sys.platform=='win32' else 'decode'))==scratch['decoderSha256']
    portable=retain('portable',ROOT/'build/lifetime-portable.json')
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    assert len(retain('backend-selection',ROOT/'build/lifetime-backend.json')['cases'])==23
    for folder,manifest in [('cache3-corpus',read(ROOT/'build/cache3-corpus/manifest.json')),
        ('wb-corpus',read(reports/'iir-cache3-fresh-wb-oracle.json'))]:
        for row in manifest['streams']:
            assert digest(ROOT/'build'/folder/'streams'/row['stream'])==row['inputSha256']
            assert digest(ROOT/'build'/folder/'oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    for backend in ['asm','c']:
        full=retain('nb-'+backend,ROOT/('build/lifetime-nb-'+backend+'/avr-verification.json'))
        old=read(reports/('prefix-nb-'+backend+'.json'));before={r['stream']:r for r in old['streams']}
        assert full['frames']==9100 and full['backend']==backend
        assert set(before)=={r['stream'] for r in full['streams']}
        assert full['binarySha256']==digest(ROOT/('build/lifetime-nb-'+backend+'/speex-test.bin'))
        for row in full['streams']:
            previous=before[row['stream']]
            assert row['frames']==previous['frames'] and row['resetVerified']
            assert (row['lspConversions'],row['lspCacheHits'])==(previous['lspConversions'],previous['lspCacheHits'])
            assert all(row[k]<previous[k] for k in ['minCycles','meanCycles','maxCycles'])
        frames=full['frames']
        for name,count in [('pitch',4096),('zero',1024),('lsp',58)]:
            extra=retain('nb-'+backend+'-'+name,ROOT/('build/lifetime-nb-'+backend+'-'+name+'/avr-verification.json'))
            assert extra['frames']==count and extra['binarySha256']==full['binarySha256']
            assert all(r['resetVerified'] for r in extra['streams']);frames+=extra['frames']
        assert frames==14278
        assert old['staticSramBytes']-full['staticSramBytes']==20
        measurements['nb-'+backend]=dict(frames=frames,beforeMeanCycles=mean(old['streams']),
            afterMeanCycles=mean(full['streams']),meanCyclesSavedPercent=100*(1-mean(full['streams'])/mean(old['streams'])),
            beforeMaxCycles=old['maxCycles'],afterMaxCycles=full['maxCycles'],
            beforeFlashBytes=old['flashBytes'],flashBytes=full['flashBytes'],beforeStaticSramBytes=old['staticSramBytes'],staticSramBytes=full['staticSramBytes'],
            beforePeakStack=2303-old['minStackPointer'],peakStack=2303-full['minStackPointer'],
            freeSram=full['minStackPointer']-256-full['staticSramBytes']+1)
        wb=retain('wb-'+backend,ROOT/('build/lifetime-wb-'+backend+'/verification.json'))
        assert wb['frames']==10563 and wb['backend']==backend
        assert wb['binarySha256']==digest(ROOT/('build/lifetime-wb-'+backend+'/wb.bin'))
        assert all(r['pcmExact'] and r['reset'] for r in wb['streams'])
        repeat=retain('wb-'+backend+'-repeats',ROOT/('build/lifetime-wb-'+backend+'-repeats/verification.json'))
        assert repeat['frames']==744 and repeat['binarySha256']==wb['binarySha256']
        assert all(r['pcmExact'] and r['reset'] for r in repeat['streams'])
        previous=read(reports/('prefix-wb-'+backend+'.json'))
        measurements['wb-'+backend]=dict(beforeMeanCycles=previous['meanCycles'],afterMeanCycles=wb['meanCycles'],
            beforeMaxCycles=previous['maxCycles'],afterMaxCycles=wb['maxCycles'],flashBytes=wb['flashBytes'],
            staticSramBytes=wb['staticSramBytes'],peakStackConservative=2303-wb['minSP'],
            freeSram=wb['minSP']-256-wb['staticSramBytes']+1)
        replay=ROOT/('build/lifetime-replay-'+backend+'/build/profile/speex-test.bin')
        assert digest(replay)==full['binarySha256']
    repeats=retain('wb-native-repeats',ROOT/'build/lifetime-wb-repeats-native/verification.json')
    assert repeats['streams']==read(reports/'prefix-wb-native-repeats.json')['streams']
    for family,mode,frames,load in [('nb','asm-normal',9100,0),('nb','asm-load40',9100,128000),
        ('nb','c-normal',9100,0),('nb','c-load10',9100,32000),('wb','normal',6467,0),('wb','load5',808,16000)]:
        folder=ROOT/('build/lifetime-'+family+'-'+mode)
        assert read(folder/'source-sha256.json')==(nb_hashes() if family=='nb' else wb_hashes())
        matrix=retain(family+'-'+mode,folder/'player-all.json')
        assert matrix['frames']==frames and matrix['includesInterrupts'] and matrix['underruns']==0
        assert matrix['extraCpuCyclesPerFrame']==load
        assert len(matrix['streams'])==(31 if family=='nb' else 16 if not load else 2)
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
    if args.rebuild:
        out=ROOT/'build/lifetime-rebuild';out.mkdir(exist_ok=True)
        for backend in ['asm','c']:
            build.run([sys.executable,ROOT/'tools/build_lsp_lifetime_test.py','--avr-gcc',args.avr_gcc,'--backend',backend])
            assert digest(ROOT/('build/lifetime-unit-'+backend+'/lifetime.bin'))==units[backend]['binarySha256']
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==kept['nb-'+backend]['binarySha256']
            wb=build_wb.avr(args.avr_gcc,backend,destination=out/('wb-'+backend))
            assert digest(wb/'wb.bin')==kept['wb-'+backend]['binarySha256']
            for load in [0,128000 if backend=='asm' else 32000]:
                build.avr(args.avr_gcc,ROOT/'build/cache3-corpus/streams/speech_ru.spxraw',load,backend)
                mode='normal' if not load else 'load40' if backend=='asm' else 'load10'
                expected=ROOT/('build/lifetime-nb-'+backend+'-'+mode+'/speech_ru/speex-player.bin')
                assert digest(ROOT/'build/player/speex-player.bin')==digest(expected)
                rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
        for mode,load in [('normal',0),('load5',16000)]:
            image=build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams/ru_pushkin_a.spxraw',load,out/('wb-'+mode))
            expected=ROOT/('build/lifetime-wb-'+mode+'/ru_pushkin_a/wb.bin')
            assert digest(image/'wb.bin')==digest(expected)
            rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
    result=dict(scope='Pinned NB3 / compact WB; ATmega328P ISA/peripheral simulation',
        baselineGitCommit=base,nbPcmBitExactToUnmodifiedXiph=True,wbPcmBitExactToExistingCompactProfile=True,
        measurements=measurements,frozenPlayerImages=images,representativePlayersRebuilt=rebuilt,
        bothDecoderBackendsRebuilt=args.rebuild,selectedCandidateReplayedBothBackends=True,
        nbSourceSha256=nb_hashes(),wbSourceSha256=wb_hashes(),
        unitSourceSha256={p:digest(ROOT/p) for p in ['src/nb3_interpolate.h','src/compact_lsp.c.inc','tests/lsp_lifetime.c',
            'tests/avr_lsp_lifetime.c','tests/verify_lsp_lifetime.mjs','tests/verify_scratch.py','tools/build_lsp_lifetime_test.py']},
        physicalBoardTested=False)
    (reports/'lifetime-admission.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: exact upstream NB / compact WB PCM, 142 frozen IRQ/PWM images and source bindings')

if __name__=='__main__':main()
