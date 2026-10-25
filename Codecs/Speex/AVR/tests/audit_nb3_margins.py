#!/usr/bin/env python3
"""Bind ASM codebook margins and fused LPC to original PCM, frozen PWM and rebuilds."""
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
    base='ab6425d';changed={'nb_decode.c.inc','compact_lsp.c.inc','nb3_interpolate.h'}
    names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',
        base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {p.name for p in (ROOT/'src').iterdir() if p.is_file()}==names|{'lsp_advance.S'}
    for name in names-changed:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert canonical(old)==canonical((ROOT/'src'/name).read_bytes()),name
    reports=ROOT/'reports';kept={};measurements={};images=[];rebuilt=[]
    def retain(name,path):
        data=read(path);shutil.copyfile(path,reports/('margin-'+name+'.json'));kept[name]=data;return data
    import prove_nb3_margins
    proof=read(reports/'margin-proof.json');assert prove_nb3_margins.prove()==proof
    certificate=retain('proof-native',ROOT/'build/margin-proof-unit/verification.json')
    assert certificate['codeTriples']==262144 and certificate['affineCertificates']==15 and certificate['affineValues']==3932160
    assert certificate['exactMaximaAgainstUntouchedXiph'] and certificate['inputAndGuardsPreserved']
    assert certificate['proofSha256']==prove_nb3_margins.canonical_hash(reports/'margin-proof.json')
    assert certificate['binarySha256']==digest(ROOT/'build/margin-proof-unit/proof.exe')
    units={};legacy={}
    for backend in ['asm','c']:
        unit=retain('unit-'+backend,ROOT/('build/margin-unit-'+backend+'/verification.json'));units[backend]=unit
        assert unit['backend']==backend and unit['cases']==1600 and unit['calls']==6208 and unit['addressCases']==3072
        for key in ['all256LowBytesAtEachRepairClassAndQuarter','oddAndPageCrossingPointers','selectorAndForcedCExact',
            'fusedAndSeparateExactAgainstUntouchedXiph','rawStateExact','guardsAndInputsPreserved','originalOracleWorkspaceGuarded',
            'calleeSavedRegistersAtRet','zeroRegisterAtRet']:assert unit[key]
        assert unit['repairMasks'][3]==0 and all(unit['repairMasks'][i]>0 for i in range(3))
        if backend=='asm':
            assert unit['exactAsmReadAndWriteAddresses'] and unit['asmCalls']==9280
            assert unit['asmReadBytes']==371200 and unit['asmWrittenBytes']==241280
            assert unit['primitiveCyclesByRepairClass']==[[181],[179],[187]] and unit['retChecks']==34048
        else:assert unit['asmCalls']==0 and unit['retChecks']==24768
        assert digest(ROOT/('build/margin-unit-'+backend+'/lifetime.bin'))==unit['binarySha256']
        old=retain('legacy-unit-'+backend,ROOT/('build/margin-legacy-unit-'+backend+'/verification.json'));legacy[backend]=old
        assert old['boundedCalls']==49680 and old['overlappingLpcOutputs']==12288 and old['lpcInputs']==4096
        for key in ['exactAgainstUntouchedXiphOnAvr','memoryOutsideLpcOutputPreserved','oracleArenaGuardsIntact',
            'calleeSavedRegistersAtRet','zeroRegisterAtRet']:assert old[key]
        assert digest(ROOT/('build/margin-legacy-unit-'+backend+'/lifetime.bin'))==old['binarySha256']
    native=read(ROOT/'build/margin-unit-c/native.log')
    assert native['cases']==524288 and native['calls']==1310720 and native['all262144CodeTriples']
    for key in ['fusedAndSeparateExactAgainstUntouchedXiph','rawStateExact','guardsAndInputsPreserved']:assert native[key]
    assert native['fineStepRepairs']>0 and native['repairMasks'][3]==0
    native.update(binarySha256=digest(ROOT/'build/margin-unit-c/native.exe'),
        compiler='Clang 24 -O2 -fwrapv -fno-strict-aliasing; separate non-LTO original Xiph oracle objects',
        sourceSha256={p:digest(ROOT/p) for p in ['src/nb3_interpolate.h','src/compact_lsp.c.inc',
            'tests/nb3_margin.c','tools/build_lsp_lifetime_test.py']})
    (reports/'margin-native-unit.json').write_text(json.dumps(native,indent=2)+'\n')
    legacy_log=(ROOT/'build/margin-legacy-unit-c/native.log').read_text()
    assert '1572880 calls' in legacy_log and '240000 LPC inputs / 720000 overlapping outputs' in legacy_log
    generic=retain('generic-unit',ROOT/'build/margin-generic-unit/verification.json')
    assert generic['calls']==82688 and generic['fullSignedMultiples16Transitions']==16384
    assert generic['exactAgainstUntouchedXiphOnAvr'] and generic['guardsIntact']
    assert digest(ROOT/'build/margin-generic-unit/quarter.bin')==generic['binarySha256']
    primitive_log=(ROOT/'build/margin-native.log').read_text()
    assert '240000 complete upstream LSP conversions' in primitive_log and '1573120 calls' in primitive_log
    scratch=retain('native-scratch',ROOT/'build/margin-native-scratch/verification.json')
    assert scratch['frames']==9100 and scratch['scratchPeak']==40 and scratch['instrumentedPushChecksEnabled'] and scratch['exactPcm']
    assert scratch['sourceSha256']=={p.relative_to(ROOT).as_posix():digest(p) for p in sorted((ROOT/'src').iterdir()) if p.is_file()}
    portable=retain('portable',ROOT/'build/margin-portable.json')
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    assert len(retain('backend-selection',ROOT/'build/margin-backend.json')['cases'])==23
    for folder,manifest in [('cache3-corpus',read(ROOT/'build/cache3-corpus/manifest.json')),
        ('wb-corpus',read(reports/'iir-cache3-fresh-wb-oracle.json'))]:
        for row in manifest['streams']:
            assert digest(ROOT/'build'/folder/'streams'/row['stream'])==row['inputSha256']
            assert digest(ROOT/'build'/folder/'oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    for backend in ['asm','c']:
        full=retain('nb-'+backend,ROOT/('build/margin-nb-'+backend+'/avr-verification.json'))
        old=read(reports/('lifetime-nb-'+backend+'.json'));before={r['stream']:r for r in old['streams']}
        assert full['frames']==9100 and full['backend']==backend
        assert set(before)=={r['stream'] for r in full['streams']}
        assert full['binarySha256']==digest(ROOT/('build/margin-nb-'+backend+'/speex-test.bin'))
        for row in full['streams']:
            previous=before[row['stream']]
            assert row['frames']==previous['frames'] and row['resetVerified']
            assert (row['lspConversions'],row['lspCacheHits'])==(previous['lspConversions'],previous['lspCacheHits'])
            if backend=='c':assert all(row[k]<previous[k] for k in ['minCycles','meanCycles','maxCycles'])
            else:
                assert row['minCycles']-previous['minCycles']<=4 and row['maxCycles']-previous['maxCycles']<=4
                assert row['meanCycles']-previous['meanCycles']<=2
        frames=full['frames']
        for name,count in [('pitch',4096),('zero',1024),('lsp',58)]:
            extra=retain('nb-'+backend+'-'+name,ROOT/('build/margin-nb-'+backend+'-'+name+'/avr-verification.json'))
            assert extra['frames']==count and extra['binarySha256']==full['binarySha256']
            assert all(r['resetVerified'] for r in extra['streams']);frames+=extra['frames']
        assert frames==14278
        assert old['staticSramBytes']==full['staticSramBytes']
        assert mean(full['streams'])<mean(old['streams']) and full['maxCycles']<old['maxCycles']
        measurements['nb-'+backend]=dict(frames=frames,beforeMeanCycles=mean(old['streams']),
            afterMeanCycles=mean(full['streams']),meanCyclesSavedPercent=100*(1-mean(full['streams'])/mean(old['streams'])),
            beforeMaxCycles=old['maxCycles'],afterMaxCycles=full['maxCycles'],
            beforeFlashBytes=old['flashBytes'],flashBytes=full['flashBytes'],beforeStaticSramBytes=old['staticSramBytes'],staticSramBytes=full['staticSramBytes'],
            beforePeakStack=2303-old['minStackPointer'],peakStack=2303-full['minStackPointer'],
            freeSram=full['minStackPointer']-256-full['staticSramBytes']+1)
        wb=retain('wb-'+backend,ROOT/('build/margin-wb-'+backend+'/verification.json'))
        assert wb['frames']==10563 and wb['backend']==backend
        assert wb['binarySha256']==digest(ROOT/('build/margin-wb-'+backend+'/wb.bin'))
        assert all(r['pcmExact'] and r['reset'] for r in wb['streams'])
        repeat=retain('wb-'+backend+'-repeats',ROOT/('build/margin-wb-'+backend+'-repeats/verification.json'))
        assert repeat['frames']==744 and repeat['binarySha256']==wb['binarySha256']
        assert all(r['pcmExact'] and r['reset'] for r in repeat['streams'])
        previous=read(reports/('lifetime-wb-'+backend+'.json'))
        measurements['wb-'+backend]=dict(beforeMeanCycles=previous['meanCycles'],afterMeanCycles=wb['meanCycles'],
            beforeMaxCycles=previous['maxCycles'],afterMaxCycles=wb['maxCycles'],flashBytes=wb['flashBytes'],
            staticSramBytes=wb['staticSramBytes'],peakStackConservative=2303-wb['minSP'],
            freeSram=wb['minSP']-256-wb['staticSramBytes']+1)
        replay=ROOT/('build/margin-replay-'+backend+'/build/profile/speex-test.bin')
        assert digest(replay)==full['binarySha256']
    repeats=retain('wb-native-repeats',ROOT/'build/margin-wb-repeats-native/verification.json')
    assert repeats['streams']==read(reports/'lifetime-wb-native-repeats.json')['streams']
    for family,mode,frames,load in [('nb','asm-normal',9100,0),('nb','asm-load40',9100,128000),
        ('nb','c-normal',9100,0),('nb','c-load10',9100,32000),('wb','normal',6467,0),('wb','load5',808,16000)]:
        folder=ROOT/('build/margin-'+family+'-'+mode)
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
        out=ROOT/'build/margin-rebuild';out.mkdir(exist_ok=True)
        for backend in ['asm','c']:
            build.run([sys.executable,ROOT/'tools/build_lsp_lifetime_test.py','--avr-gcc',args.avr_gcc,'--backend',backend,'--mode','margin'])
            assert digest(ROOT/('build/margin-unit-'+backend+'/lifetime.bin'))==units[backend]['binarySha256']
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==kept['nb-'+backend]['binarySha256']
            wb=build_wb.avr(args.avr_gcc,backend,destination=out/('wb-'+backend))
            assert digest(wb/'wb.bin')==kept['wb-'+backend]['binarySha256']
            for load in [0,128000 if backend=='asm' else 32000]:
                build.avr(args.avr_gcc,ROOT/'build/cache3-corpus/streams/speech_ru.spxraw',load,backend)
                mode='normal' if not load else 'load40' if backend=='asm' else 'load10'
                expected=ROOT/('build/margin-nb-'+backend+'-'+mode+'/speech_ru/speex-player.bin')
                assert digest(ROOT/'build/player/speex-player.bin')==digest(expected)
                rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
        for mode,load in [('normal',0),('load5',16000)]:
            image=build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams/ru_pushkin_a.spxraw',load,out/('wb-'+mode))
            expected=ROOT/('build/margin-wb-'+mode+'/ru_pushkin_a/wb.bin')
            assert digest(image/'wb.bin')==digest(expected)
            rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
    result=dict(scope='Pinned NB3 / compact WB; ATmega328P ISA/peripheral simulation',
        baselineGitCommit=base,primaryTarget='AVR ASM; portable C fallback verified',nbPcmBitExactToUnmodifiedXiph=True,wbPcmBitExactToExistingCompactProfile=True,
        measurements=measurements,frozenPlayerImages=images,representativePlayersRebuilt=rebuilt,
        bothDecoderBackendsRebuilt=args.rebuild,selectedCandidateReplayedBothBackends=True,
        nbSourceSha256=nb_hashes(),wbSourceSha256=wb_hashes(),
        unitSourceSha256={p:digest(ROOT/p) for p in ['src/nb3_interpolate.h','src/compact_lsp.c.inc','src/lsp_advance.S',
            'tests/nb3_margin.c','tests/avr_nb3_margin.c','tests/verify_nb3_margin.mjs','tools/build_lsp_lifetime_test.py',
            'tests/verify_avr.mjs','tests/verify_lsp_lifetime.mjs','tests/verify_scratch.py']},
        physicalBoardTested=False)
    (reports/'margin-admission.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: exact upstream NB / compact WB PCM, 142 frozen IRQ/PWM images and source bindings')

if __name__=='__main__':main()
