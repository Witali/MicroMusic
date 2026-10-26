#!/usr/bin/env python3
"""Bind private r1 liveness to exact PCM, IRQ preemption and frozen PWM images."""
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
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(b):return b.replace(b'\r\n',b'\n')
def mean(d):return sum(r['frames']*r['meanCycles'] for r in d['streams'])/d['frames']
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rebuild',action='store_true');p.add_argument('--avr-gcc');args=p.parse_args()
    if args.rebuild and not args.avr_gcc:p.error('--rebuild requires --avr-gcc')
    build.verify_sources();base='ddd4f01e';reports=ROOT/'reports'
    names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {p.name for p in (ROOT/'src').iterdir() if p.is_file()}==names
    for name in names-{'q14_macros.S','lsp_stage.S'}:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert canonical(old)==canonical((ROOT/'src'/name).read_bytes()),name
    proof=read(reports/'zero-kernel-proof.json')
    for name,value in proof['sourceSha256'].items():assert digest(ROOT/name)==value,name
    assert proof['defaultQ14MathImageByteIdentical'] and proof['explicitCStageUnitByteIdentical']
    assert digest(ROOT/'build/math/math.bin')==proof['mathImageSha256']==read(reports/'poly-q14-refactor.json')['afterMathImageSha256']
    assert digest(ROOT/'build/zero-stage-unit-c/stage.bin')==proof['cStageUnitSha256']==read(reports/'poly-stage-unit-c.json')['binarySha256']
    cClosure={n:h for n,h in nb_hashes().items() if not n.endswith('.S')}
    assert cClosure==proof['unchangedCCompilationSourceSha256']
    wbClosure={n:h for n,h in wb_hashes().items() if not n.endswith('.S')}
    assert wbClosure=={n:h for n,h in read(ROOT/'build/first-wb-normal/source-sha256.json').items() if not n.endswith('.S')}
    for family,name in [('nb','speex-test.bin'),('wb','wb.bin')]:
        assert digest(ROOT/('build/zero-'+family+'-c')/name)==proof['cDecoderImagesByteIdentical'][family]
        old=read(reports/('first-'+family+'-c.json'));assert old['binarySha256']==proof['cDecoderImagesByteIdentical'][family]
    stage=read(reports/'zero-stage-unit-asm.json');irq=read(reports/'zero-stage-irq.json')
    assert digest(ROOT/'build/zero-stage-unit-asm/stage.bin')==stage['binarySha256']
    assert stage['cases']==256254 and stage['outputsPerPath']==1025016 and stage['retChecks']==768762
    assert stage['primitiveCyclesIncludingRet']=={'2':[238],'3':[327],'4':[416]}
    assert stage['asmReadBytes']==3075048 and stage['asmWrittenBytes']==4100064 and stage['savedStackBytes']==12
    assert digest(ROOT/'build/zero-stage-irq/irq.bin')==irq['binarySha256']
    assert irq['injections']==15687 and irq['nonzeroR1Interrupts']==3668 and irq['isrMulInstructions']==15687
    for key in ['everyInstructionBoundaryPreempted','all32RegistersAndSregRestoredAtReti','interruptReturnPcAndSpExact',
        'selectedAndForcedCExact','independentBigIntProductOracle','guardsAndUntouchedWordsPreserved','externalR1Zero']:assert irq[key]
    def retain(name,path):
        data=read(path);shutil.copyfile(path,reports/('zero-'+name+'.json'));return data
    geometry=retain('geometry-unit-asm',ROOT/'build/zero-geometry-unit-asm/verification.json')
    assert geometry['cases']==1600 and geometry['calls']==6208 and geometry['addressCases']==3072 and geometry['retChecks']==34048
    for key in ['selectorAndForcedCExact','fusedAndSeparateExactAgainstUntouchedXiph','rawStateExact','guardsAndInputsPreserved',
        'calleeSavedRegistersAtRet','zeroRegisterAtRet']:assert geometry[key]
    assert digest(ROOT/'build/zero-geometry-unit-asm/lifetime.bin')==geometry['binarySha256']
    legacy=retain('legacy-unit-asm',ROOT/'build/zero-legacy-unit-asm/verification.json')
    assert legacy['boundedCalls']==49680 and legacy['overlappingLpcOutputs']==12288 and legacy['lpcInputs']==4096
    for key in ['exactAgainstUntouchedXiphOnAvr','memoryOutsideLpcOutputPreserved','oracleArenaGuardsIntact',
        'calleeSavedRegistersAtRet','zeroRegisterAtRet']:assert legacy[key]
    assert digest(ROOT/'build/zero-legacy-unit-asm/lifetime.bin')==legacy['binarySha256']
    for folder,manifest in [('cache3-corpus',read(ROOT/'build/cache3-corpus/manifest.json')),
        ('wb-corpus',read(reports/'iir-cache3-fresh-wb-oracle.json'))]:
        for row in manifest['streams']:
            assert digest(ROOT/'build'/folder/'streams'/row['stream'])==row['inputSha256']
            assert digest(ROOT/'build'/folder/'oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    full=retain('nb-asm',ROOT/'build/zero-nb-asm/avr-verification.json');before=read(reports/'first-nb-asm.json')
    assert full['frames']==9100 and full['backend']=='asm'
    assert full['binarySha256']==digest(ROOT/'build/zero-nb-asm/speex-test.bin')
    old={r['stream']:r for r in before['streams']};assert set(old)=={r['stream'] for r in full['streams']}
    for row in full['streams']:
        previous=old[row['stream']];assert row['frames']==previous['frames'] and row['resetVerified']
        assert (row['lspConversions'],row['lspCacheHits'])==(previous['lspConversions'],previous['lspCacheHits'])
        for key in ['minCycles','meanCycles','maxCycles']:assert row[key]<=previous[key]
    for label,count in [('pitch',4096),('zero',1024),('lsp',58)]:
        extra=retain('nb-asm-'+label,ROOT/('build/zero-nb-asm-'+label+'/avr-verification.json'))
        assert extra['frames']==count and extra['binarySha256']==full['binarySha256'] and all(r['resetVerified'] for r in extra['streams'])
    assert (full['flashBytes'],full['staticSramBytes'],full['minStackPointer'])==(10986,1099,before['minStackPointer'])
    wb=retain('wb-asm',ROOT/'build/zero-wb-asm/verification.json');oldWb=read(reports/'first-wb-asm.json')
    assert wb['frames']==10563 and wb['binarySha256']==digest(ROOT/'build/zero-wb-asm/wb.bin')
    previous={r['name']:r for r in oldWb['streams']};assert set(previous)=={r['name'] for r in wb['streams']}
    for row in wb['streams']:
        assert row['pcmExact'] and row['reset']
        for key in ['minCycles','meanCycles','maxCycles']:assert row[key]<=previous[row['name']][key]
    repeat=retain('wb-asm-repeats',ROOT/'build/zero-wb-asm-repeats/verification.json')
    assert repeat['frames']==744 and repeat['binarySha256']==wb['binarySha256']
    assert all(r['pcmExact'] and r['reset'] for r in repeat['streams'])
    assert (wb['flashBytes'],wb['staticSramBytes'],wb['minSP'])==(17484,1279,oldWb['minSP'])
    measurements={}
    for family,old,new,avg in [('nb',before,full,mean),('wb',oldWb,wb,lambda d:d['meanCycles'])]:
        assert avg(new)<avg(old) and new['maxCycles']<old['maxCycles']
        measurements[family+'-asm']=dict(beforeMeanCycles=avg(old),afterMeanCycles=avg(new),meanCyclesSavedPercent=100*(1-avg(new)/avg(old)),
            beforeMaxCycles=old['maxCycles'],maxCycles=new['maxCycles'],beforeFlashBytes=old['flashBytes'],flashBytes=new['flashBytes'],
            staticSramBytes=new['staticSramBytes'],stack=2303-new['minStackPointer' if family=='nb' else 'minSP'])
    images=[];reused=[]
    for family,mode,frames,load in [('nb','asm-normal',9100,0),('nb','asm-load40',9100,128000),('wb','normal',6467,0),('wb','load5',808,16000),
        ('nb','c-normal',9100,0),('nb','c-load10',9100,32000)]:
        reuse=mode.startswith('c-');folder=ROOT/('build/'+('first-' if reuse else 'zero-')+family+'-'+mode)
        frozen=read(folder/'source-sha256.json')
        if reuse:assert {n:h for n,h in frozen.items() if not n.endswith('.S')}==cClosure
        else:assert frozen==(nb_hashes() if family=='nb' else wb_hashes())
        matrix=read(folder/'player-all.json') if reuse else retain(family+'-'+mode,folder/'player-all.json')
        assert matrix['frames']==frames and matrix['includesInterrupts'] and matrix['underruns']==0 and matrix['extraCpuCyclesPerFrame']==load
        assert len(matrix['streams'])==(31 if family=='nb' else 16 if not load else 2)
        for row in matrix['streams']:
            name=Path(row['input']['file']);image=folder/name.stem;binary=image/('speex-player.bin' if family=='nb' else 'wb.bin')
            corpus=ROOT/'build'/('cache3-corpus' if family=='nb' else 'wb-corpus')
            assert digest(corpus/'streams'/name)==row['input']['sha256'] and digest(binary)==row['binarySha256']
            expected=bytes(b^128 for b in (corpus/'oracle'/(name.stem+'.pcm')).read_bytes()[1::2])
            assert (image/'player-pwm.u8').read_bytes()==expected and hashlib.sha256(expected).hexdigest()==row['pwmSha256']
            assert row['staticSramBytes']+row['peakStackBytes']+row['freeSramAtPeak']==2048
            assert row['underruns']==0 and row['minQueuedSamplesBeforeOutput']>0
            if load:assert row['measuredExtraLoadCount']==row['frames']
            (reused if reuse else images).append(dict(image=binary.relative_to(ROOT).as_posix(),sha256=row['binarySha256']))
    assert len(images)==80 and len(reused)==62
    rebuilt=[]
    if args.rebuild:
        out=ROOT/'build/zero-rebuild';out.mkdir(exist_ok=True)
        for kind,script,filename,evidence in [('stage','build_lsp_stage_test.py','stage.bin',stage),('irq','build_lsp_stage_irq_test.py','irq.bin',irq)]:
            args2=['--backend','asm'] if kind=='stage' else []
            build.run([sys.executable,ROOT/'tools'/script,'--avr-gcc',args.avr_gcc,*args2,'--out',out/kind])
            assert digest(out/kind/filename)==evidence['binarySha256']
        for backend in ['asm','c']:
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==(full['binarySha256'] if backend=='asm' else proof['cDecoderImagesByteIdentical']['nb'])
            image=build_wb.avr(args.avr_gcc,backend,destination=out/('wb-'+backend))
            assert digest(image/'wb.bin')==(wb['binarySha256'] if backend=='asm' else proof['cDecoderImagesByteIdentical']['wb'])
            for load in [0,128000 if backend=='asm' else 32000]:
                build.avr(args.avr_gcc,ROOT/'build/cache3-corpus/streams/speech_ru.spxraw',load,backend)
                expected=ROOT/('build/'+('zero' if backend=='asm' else 'first')+'-nb-'+backend+'-'+('normal' if not load else 'load40' if backend=='asm' else 'load10')+'/speech_ru/speex-player.bin')
                assert digest(ROOT/'build/player/speex-player.bin')==digest(expected)
                rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
        for mode,load in [('normal',0),('load5',16000)]:
            image=build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams/ru_pushkin_a.spxraw',load,out/('wb-'+mode))
            expected=ROOT/('build/zero-wb-'+mode+'/ru_pushkin_a/wb.bin');assert digest(image/'wb.bin')==digest(expected)
            rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
        build.run([sys.executable,ROOT/'tools/build_math_test.py','--avr-gcc',args.avr_gcc])
        assert digest(ROOT/'build/math/math.bin')==proof['mathImageSha256']
    sourceFiles=['tests/audit_lsp_zero.py','tests/verify_avr.mjs','tests/verify_wb.mjs','tools/build_lsp_lifetime_test.py',
        'tests/verify_nb3_margin.mjs','tests/verify_lsp_lifetime.mjs',*proof['sourceSha256']]
    result=dict(baselineGitCommit=base,primaryTarget='ATmega328P AVR ASM, 16 MHz / 2 KB SRAM',measurements=measurements,
        nbPcmBitExactToUnmodifiedXiph=True,wbPcmBitExactToExistingCompactProfile=True,newlyFrozenAsmPlayerImages=images,
        reusedBaselineCPlayerImages=reused,cEvidenceReuseReason='Unchanged complete C compilation dependencies and byte-identical rebuilt NB/WB C decoders; same 62 previously executed baseline C player binaries, not fresh simulation runs',
        cCompilationSourceSha256=cClosure,wbCCompilationSourceSha256=wbClosure,
        nbSourceSha256=nb_hashes(),wbSourceSha256=wb_hashes(),sourceSha256={n:digest(ROOT/n) for n in sourceFiles},
        bothDecoderBackendsRebuilt=args.rebuild,representativePlayersRebuilt=rebuilt,
        kernelProof='reports/zero-kernel-proof.json',syntheticIrqProof='reports/zero-stage-irq.json',physicalBoardTested=False)
    (reports/'zero-admission.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('PASS: exact PCM, exhaustive instruction-boundary IRQ, 80 fresh ASM and 62 unchanged baseline C PWM images')
if __name__=='__main__':main()
