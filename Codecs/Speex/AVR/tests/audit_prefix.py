#!/usr/bin/env python3
"""Bind exact NB prefix decoding to original PCM, frozen PWM and rebuilds."""
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
    base='03fad82';changed={'nb_decode.c.inc','speex_avr.c'}
    names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',
        base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {p.name for p in (ROOT/'src').iterdir() if p.is_file()}==names|{'nb3_lsp.h'}
    for name in names-changed:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert canonical(old)==canonical((ROOT/'src'/name).read_bytes()),name
    reports=ROOT/'reports';kept={};measurements={};images=[];rebuilt=[]
    def retain(name,path):
        data=read(path);shutil.copyfile(path,reports/('prefix-'+name+'.json'));kept[name]=data;return data
    unit=retain('unit',ROOT/'build/prefix-unit/verification.json')
    assert unit['cases']==270336 and unit['angleComparisons']==2703360 and not unit['arithmeticAsmEnabled']
    for key in ['all262144CodeTriples','quartersAndGainExact','onlyFirstFourPacketBytesRead',
        'inputAndGuardsPreserved','originalTablesPreserved','calleeSavedRegistersAtRet','zeroRegisterAtRet']:assert unit[key]
    assert (unit['minRaw'],unit['maxRaw'])==(96,24880)
    assert digest(ROOT/'build/prefix-unit/prefix.bin')==unit['binarySha256']
    log=(ROOT/'build/prefix-unit/native.log').read_text()
    assert '8388608 complete LSP/gain combinations' in log and 'raw range 96..24880' in log
    native=dict(cases=8388608,all18BitLspAnd5BitGainCombinations=True,quartersAndGainExact=True,
        oracle='Untouched Xiph quant_lsp.c, bits.c and original tables; separately compiled non-LTO objects',
        compiler='Clang 24 -std=c11 -O2 -fwrapv -fno-strict-aliasing',minRaw=96,maxRaw=24880,
        binarySha256=digest(ROOT/'build/prefix-unit/native.exe'),
        sourceSha256={p:digest(ROOT/p) for p in ['src/nb3_lsp.h','tests/prefix.c','tools/build_prefix_test.py']})
    (reports/'prefix-native-unit.json').write_text(json.dumps(native,indent=2)+'\n')
    portable=retain('portable',ROOT/'build/prefix-portable.json')
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    assert len(retain('backend-selection',ROOT/'build/prefix-backend.json')['cases'])==23
    for folder,manifest in [('cache3-corpus',read(ROOT/'build/cache3-corpus/manifest.json')),
        ('wb-corpus',read(reports/'iir-cache3-fresh-wb-oracle.json'))]:
        for row in manifest['streams']:
            assert digest(ROOT/'build'/folder/'streams'/row['stream'])==row['inputSha256']
            assert digest(ROOT/'build'/folder/'oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    for backend in ['asm','c']:
        full=retain('nb-'+backend,ROOT/('build/prefix-nb-'+backend+'/avr-verification.json'))
        old=read(reports/('subframe-nb-'+backend+'.json'));before={r['stream']:r for r in old['streams']}
        assert full['frames']==9100 and full['backend']==backend
        assert set(before)=={r['stream'] for r in full['streams']}
        assert full['binarySha256']==digest(ROOT/('build/prefix-nb-'+backend+'/speex-test.bin'))
        for row in full['streams']:
            previous=before[row['stream']]
            assert row['frames']==previous['frames'] and row['resetVerified']
            assert (row['lspConversions'],row['lspCacheHits'])==(previous['lspConversions'],previous['lspCacheHits'])
            assert all(row[k]<previous[k] for k in ['minCycles','meanCycles','maxCycles'])
        frames=full['frames']
        for name,count in [('pitch',4096),('zero',1024),('lsp',58)]:
            extra=retain('nb-'+backend+'-'+name,ROOT/('build/prefix-nb-'+backend+'-'+name+'/avr-verification.json'))
            assert extra['frames']==count and extra['binarySha256']==full['binarySha256']
            assert all(r['resetVerified'] for r in extra['streams']);frames+=extra['frames']
        assert frames==14278
        measurements['nb-'+backend]=dict(frames=frames,beforeMeanCycles=mean(old['streams']),
            afterMeanCycles=mean(full['streams']),meanCyclesSavedPercent=100*(1-mean(full['streams'])/mean(old['streams'])),
            beforeMaxCycles=old['maxCycles'],afterMaxCycles=full['maxCycles'],
            beforeFlashBytes=old['flashBytes'],flashBytes=full['flashBytes'],staticSramBytes=full['staticSramBytes'],
            beforePeakStack=2303-old['minStackPointer'],peakStack=2303-full['minStackPointer'],
            freeSram=full['minStackPointer']-256-full['staticSramBytes']+1)
        wb=retain('wb-'+backend,ROOT/('build/prefix-wb-'+backend+'/verification.json'))
        assert wb['frames']==10563 and wb['backend']==backend
        assert wb['binarySha256']==digest(ROOT/('build/prefix-wb-'+backend+'/wb.bin'))
        assert all(r['pcmExact'] and r['reset'] for r in wb['streams'])
        repeat=retain('wb-'+backend+'-repeats',ROOT/('build/prefix-wb-'+backend+'-repeats/verification.json'))
        assert repeat['frames']==744 and repeat['binarySha256']==wb['binarySha256']
        assert all(r['pcmExact'] and r['reset'] for r in repeat['streams'])
        previous=read(reports/('subframe-wb-'+backend+'.json'))
        measurements['wb-'+backend]=dict(beforeMeanCycles=previous['meanCycles'],afterMeanCycles=wb['meanCycles'],
            beforeMaxCycles=previous['maxCycles'],afterMaxCycles=wb['maxCycles'],flashBytes=wb['flashBytes'],
            staticSramBytes=wb['staticSramBytes'],peakStackConservative=2303-wb['minSP'],
            freeSram=wb['minSP']-256-wb['staticSramBytes']+1)
        replay=ROOT/('build/prefix-replay-'+backend+'/build/profile/speex-test.bin')
        assert digest(replay)==full['binarySha256']
    repeats=retain('wb-native-repeats',ROOT/'build/prefix-wb-repeats-native/verification.json')
    assert repeats['streams']==read(reports/'subframe-wb-native-repeats.json')['streams']
    for family,mode,frames,load in [('nb','asm-normal',9100,0),('nb','asm-load40',9100,128000),
        ('nb','c-normal',9100,0),('nb','c-load10',9100,32000),('wb','normal',6467,0),('wb','load5',808,16000)]:
        folder=ROOT/('build/prefix-'+family+'-'+mode)
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
        out=ROOT/'build/prefix-rebuild';out.mkdir(exist_ok=True)
        build.run([sys.executable,ROOT/'tools/build_prefix_test.py','--avr-gcc',args.avr_gcc])
        assert digest(ROOT/'build/prefix-unit/prefix.bin')==unit['binarySha256']
        for backend in ['asm','c']:
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==kept['nb-'+backend]['binarySha256']
            wb=build_wb.avr(args.avr_gcc,backend,destination=out/('wb-'+backend))
            assert digest(wb/'wb.bin')==kept['wb-'+backend]['binarySha256']
            for load in [0,128000 if backend=='asm' else 32000]:
                build.avr(args.avr_gcc,ROOT/'build/cache3-corpus/streams/speech_ru.spxraw',load,backend)
                mode='normal' if not load else 'load40' if backend=='asm' else 'load10'
                expected=ROOT/('build/prefix-nb-'+backend+'-'+mode+'/speech_ru/speex-player.bin')
                assert digest(ROOT/'build/player/speex-player.bin')==digest(expected)
                rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
        for mode,load in [('normal',0),('load5',16000)]:
            image=build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams/ru_pushkin_a.spxraw',load,out/('wb-'+mode))
            expected=ROOT/('build/prefix-wb-'+mode+'/ru_pushkin_a/wb.bin')
            assert digest(image/'wb.bin')==digest(expected)
            rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
    result=dict(scope='Pinned NB3 / compact WB; ATmega328P ISA/peripheral simulation',
        baselineGitCommit=base,nbPcmBitExactToUnmodifiedXiph=True,wbPcmBitExactToExistingCompactProfile=True,
        measurements=measurements,frozenPlayerImages=images,representativePlayersRebuilt=rebuilt,
        bothDecoderBackendsRebuilt=args.rebuild,selectedCandidateReplayedBothBackends=True,
        nbSourceSha256=nb_hashes(),wbSourceSha256=wb_hashes(),
        unitSourceSha256={p:digest(ROOT/p) for p in ['src/nb3_lsp.h','tests/prefix.c',
            'tests/avr_prefix.c','tests/verify_prefix.mjs','tools/build_prefix_test.py']},
        physicalBoardTested=False)
    (reports/'prefix-admission.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: exact upstream NB / compact WB PCM, 142 frozen IRQ/PWM images and source bindings')

if __name__=='__main__':main()
