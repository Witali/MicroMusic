#!/usr/bin/env python3
"""Bind combined NB packet-reader timing to sources, original PCM and PWM."""
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
    base='db52a40';changed={'nb_decode.c.inc','innovation.h','short_pitch.h','speex_avr.c'}
    names=set(subprocess.check_output(['git','ls-tree','--full-tree','--name-only',
        base+':Codecs/Speex/AVR/src'],cwd=ROOT,text=True).splitlines())
    assert {p.name for p in (ROOT/'src').iterdir() if p.is_file()}==names|{'nb3_subframe.h'}
    for name in names-changed:
        old=subprocess.check_output(['git','show',base+':Codecs/Speex/AVR/src/'+name],cwd=ROOT)
        assert canonical(old)==canonical((ROOT/'src'/name).read_bytes()),name
    reports=ROOT/'reports';kept={};measurements={};images=[];rebuilt=[]
    def retain(name,path):
        data=read(path);shutil.copyfile(path,reports/('subframe-'+name+'.json'));kept[name]=data;return data
    unit=retain('unit',ROOT/'build/subframe-unit/verification.json')
    assert unit['casesPerImplementation']==115712 and unit['exact'] and not unit['asmEnabled']
    for key in ['inputReadAddressesChecked','noReadsBeyond20BytePacket','fiveByteWindowsOnly',
        'packetAndGuardsIntact','calleeSavedRegistersAtRet','zeroRegisterAtRet','previousGenericCursorExact']:assert unit[key]
    assert digest(ROOT/'build/subframe-unit/subframe.bin')==unit['binarySha256']
    native_log=(ROOT/'build/subframe-unit/native.log').read_text()
    assert '4227072 packet groups' in native_log
    native=dict(cases=4227072,all20BitIndexGroupsAtEachSubframe=True,all8192HeadersAtEachSubframe=True,
        exact=True,compiler='Clang 24 -std=c11 -O2 -fwrapv -fno-strict-aliasing',
        binarySha256=digest(ROOT/'build/subframe-unit/native.exe'),
        sourceSha256={p:digest(ROOT/p) for p in ['src/nb3_subframe.h','tests/subframe.c']})
    (reports/'subframe-native-unit.json').write_text(json.dumps(native,indent=2)+'\n')
    short=retain('short-unit',ROOT/'build/subframe-short-final.json')
    assert short['blocks']==49152 and short['samplesPerBackend']==1966080 and short['exact']
    for key in ['historyPreserved','packetPreserved','guardsIntact','bitConsumptionExact',
        'calleeSavedRegistersPreserved','zeroRegisterRestored','indexParsingOutsideMeasuredController']:assert short[key]
    assert digest(ROOT/'build/short-pitch-unit/short-pitch.bin')==short['binarySha256']
    portable=retain('portable',ROOT/'build/subframe-portable.json')
    assert portable['testedStaticArchives']==2 and portable['frames']==9100
    assert portable['wideband']['frames']==10563 and portable['wideband']['invalidCallsAndResetVerified']
    assert len(retain('backend-selection',ROOT/'build/subframe-backend.json')['cases'])==23
    probe=retain('stack-probe',ROOT/'build/subframe-stack-probe/verification.json')
    assert len(probe['rows'])==4 and not probe['includesInterrupts']
    for row in probe['rows']:
        assert row['frames']==136 and row['noStackAccessBetweenByteWrites']
        assert row['rawPeakStack']>=row['completedPairPeakStack']
    for folder,manifest in [('cache3-corpus',read(ROOT/'build/cache3-corpus/manifest.json')),
        ('wb-corpus',read(reports/'iir-cache3-fresh-wb-oracle.json'))]:
        for row in manifest['streams']:
            assert digest(ROOT/'build'/folder/'streams'/row['stream'])==row['inputSha256']
            assert digest(ROOT/'build'/folder/'oracle'/(Path(row['stream']).stem+'.pcm'))==row['pcmSha256']
    for backend in ['asm','c']:
        full=retain('nb-'+backend,ROOT/('build/subframe-nb-'+backend+'/avr-verification.json'))
        old=read(reports/('lsp-quarter-nb-'+backend+'.json'));before={r['stream']:r for r in old['streams']}
        assert full['frames']==9100 and full['backend']==backend
        assert set(before)=={r['stream'] for r in full['streams']}
        assert full['binarySha256']==digest(ROOT/('build/subframe-nb-'+backend+'/speex-test.bin'))
        for row in full['streams']:
            previous=before[row['stream']]
            assert row['frames']==previous['frames'] and row['resetVerified']
            assert (row['lspConversions'],row['lspCacheHits'])==(previous['lspConversions'],previous['lspCacheHits'])
            assert all(row[k]<previous[k] for k in ['minCycles','meanCycles','maxCycles'])
        frames=full['frames']
        for name,count in [('pitch',4096),('zero',1024),('lsp',58)]:
            extra=retain('nb-'+backend+'-'+name,ROOT/('build/subframe-nb-'+backend+'-'+name+'/avr-verification.json'))
            assert extra['frames']==count and extra['binarySha256']==full['binarySha256']
            assert all(r['resetVerified'] for r in extra['streams']);frames+=extra['frames']
        assert frames==14278
        measurements['nb-'+backend]=dict(frames=frames,beforeMeanCycles=mean(old['streams']),
            afterMeanCycles=mean(full['streams']),meanCyclesSavedPercent=100*(1-mean(full['streams'])/mean(old['streams'])),
            beforeMaxCycles=old['maxCycles'],afterMaxCycles=full['maxCycles'],
            beforeFlashBytes=old['flashBytes'],flashBytes=full['flashBytes'],staticSramBytes=full['staticSramBytes'],
            beforePeakStack=2303-old['minStackPointer'],peakStack=2303-full['minStackPointer'],
            freeSram=full['minStackPointer']-256-full['staticSramBytes']+1)
        wb=retain('wb-'+backend,ROOT/('build/subframe-wb-'+backend+'/verification.json'))
        assert wb['frames']==10563 and wb['backend']==backend
        assert wb['binarySha256']==digest(ROOT/('build/subframe-wb-'+backend+'/wb.bin'))
        assert all(r['pcmExact'] and r['reset'] for r in wb['streams'])
        repeat=retain('wb-'+backend+'-repeats',ROOT/('build/subframe-wb-'+backend+'-repeats/verification.json'))
        assert repeat['frames']==744 and repeat['binarySha256']==wb['binarySha256']
        measurements['wb-'+backend]={k:v for k,v in wb.items() if k!='streams'}
    assert digest(ROOT/'build/subframe-stack-probe/verify.mjs')==probe['observerSourceSha256']
    for row in probe['rows']:
        previous=read(reports/('lsp-quarter-wb-'+row['backend']+'.json'))
        expected=previous if row['state']=='before' else kept['wb-'+row['backend']]
        assert row['binarySha256']==expected['binarySha256']
    repeats=retain('wb-native-repeats',ROOT/'build/subframe-wb-repeats-native/verification.json')
    assert repeats['streams']==read(reports/'lsp-quarter-wb-repeats-native.json')['streams']
    for family,mode,frames,load in [('nb','asm-normal',9100,0),('nb','asm-load40',9100,128000),
        ('nb','c-normal',9100,0),('nb','c-load10',9100,32000),('wb','normal',6467,0),('wb','load5',808,16000)]:
        folder=ROOT/('build/subframe-'+family+'-'+mode)
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
    if args.rebuild:
        out=ROOT/'build/subframe-rebuild';out.mkdir(exist_ok=True)
        build.run([sys.executable,ROOT/'tools/build_subframe_test.py','--avr-gcc',args.avr_gcc])
        assert digest(ROOT/'build/subframe-unit/subframe.bin')==unit['binarySha256']
        for backend in ['asm','c']:
            build.avr(args.avr_gcc,backend=backend)
            assert digest(ROOT/'build/profile/speex-test.bin')==kept['nb-'+backend]['binarySha256']
            wb=build_wb.avr(args.avr_gcc,backend,destination=out/('wb-'+backend))
            assert digest(wb/'wb.bin')==kept['wb-'+backend]['binarySha256']
            for load in [0,128000 if backend=='asm' else 32000]:
                build.avr(args.avr_gcc,ROOT/'build/cache3-corpus/streams/speech_ru.spxraw',load,backend)
                mode='normal' if not load else 'load40' if backend=='asm' else 'load10'
                expected=ROOT/('build/subframe-nb-'+backend+'-'+mode+'/speech_ru/speex-player.bin')
                assert digest(ROOT/'build/player/speex-player.bin')==digest(expected)
                rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
        for mode,load in [('normal',0),('load5',16000)]:
            image=build_wb.avr(args.avr_gcc,'asm',ROOT/'build/wb-corpus/streams/ru_pushkin_a.spxraw',load,out/('wb-'+mode))
            expected=ROOT/('build/subframe-wb-'+mode+'/ru_pushkin_a/wb.bin')
            assert digest(image/'wb.bin')==digest(expected)
            rebuilt.append(dict(image=expected.relative_to(ROOT).as_posix(),sha256=digest(expected)))
    result=dict(scope='Pinned NB3 / compact WB; ATmega328P ISA/peripheral simulation',
        baselineGitCommit=base,measurements=measurements,frozenPlayerImages=images,
        representativePlayersRebuilt=rebuilt,bothDecoderBackendsRebuilt=args.rebuild,
        nbSourceSha256=nb_hashes(),wbSourceSha256=wb_hashes(),
        unitSourceSha256={p:digest(ROOT/p) for p in ['src/nb3_subframe.h','tests/subframe.c',
            'tests/avr_subframe.c','tests/verify_subframe.mjs','tools/build_subframe_test.py',
            'tests/probe_wb_stack.py']},
        physicalBoardTested=False)
    for backend in ['asm','c']:
        replay=ROOT/('build/subframe-replay-'+backend+'/speex-test.bin')
        assert digest(replay)==kept['nb-'+backend]['binarySha256']
    result['selectedCandidateReplayedBothBackends']=True
    (reports/'subframe-admission.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: 142 frozen PWM images, upstream NB / compact WB PCM, both backends and source bindings')

if __name__=='__main__':main()
