#!/usr/bin/env python3
"""Audit exact zero-vector dispatch, arithmetic and complete output evidence."""
import argparse
import json
from pathlib import Path
import re
from audit_nb1_gain import ROOT,sha,read,save
OUT=ROOT/'build/zero-synthesis-final'
CHANGED=['src/lowrate_excitation.h','src/nb1_vocoder.h','src/nb1_vocoder.c','src/nb1_vocoder.S',
         'tests/verify_low_api.mjs','tests/verify_nb1_streaming.mjs']
ADDED=['tests/avr_nb1_zero_vocoder.c','tests/build_nb1_zero_vocoder.py','tests/verify_nb1_zero_vocoder.mjs',
       'tests/verify_nb1_zero_context.py','tests/build_nb1_zero_synthesis.py','tests/run_nb1_zero_synthesis.py',
       'tests/audit_nb1_zero_synthesis.py']


def timing(corpus,*,out=OUT):
    traces=[json.loads((out/e/'wb395/packet-timing.json').read_text()) for e in ['before','after']]
    assert all(t['frames']==10627 and len(t['streams'])==18 for t in traces)
    gains=list(map(int,re.search(r'ol_gain_table\[32\]=\{([^}]+)\}',(ROOT/'vendor/speex-1.2.1/libspeex/nb_celp.c').read_text())[1].split(',')))
    groups={name:dict(frames=0,beforeCycles=0,afterCycles=0,deltaMin=None,deltaMax=None) for name in ['zero','ordinary']}
    speech=dict(frames=0,zeroContextFrames=0,beforeCycles=0,afterCycles=0);streams=[]
    for a,b in zip(traces[0]['streams'],traces[1]['streams']):
        for k in ['stream','inputSha256','pcmSha256']:assert a[k]==b[k]
        path=corpus/'wb395/streams'/a['stream'];assert sha(path,False)==a['inputSha256'];data=path.read_bytes()
        assert len(a['cycles'])==len(b['cycles'])==len(data)//10
        natural=a['stream'].startswith(('en_','ru_'));zero_frames=0
        for i,(x,y) in enumerate(zip(a['cycles'],b['cycles'])):
            p=i*10;assert data[p]>>3==1
            code=((data[p+3]&3)<<2)|(data[p+4]>>6);scale=(28406*gains[(data[p+4]>>1)&31])//32768
            zero=code<4 or scale<=4096;zero_frames+=zero;g=groups['zero' if zero else 'ordinary'];d=y-x
            g['frames']+=1;g['beforeCycles']+=x;g['afterCycles']+=y
            g['deltaMin']=d if g['deltaMin'] is None else min(g['deltaMin'],d)
            g['deltaMax']=d if g['deltaMax'] is None else max(g['deltaMax'],d)
        row=dict(stream=a['stream'],frames=len(a['cycles']),zeroContextFrames=zero_frames,beforeCycles=sum(a['cycles']),afterCycles=sum(b['cycles']))
        if natural:
            for k in speech:speech[k]+=row[k]
        streams.append(row)
    for epoch in ['before','after']:
        speech[epoch+'MeanCycles']=speech[epoch+'Cycles']/speech['frames']
        speech[epoch+'CpuPercent']=speech[epoch+'MeanCycles']/3200
    return dict(scope='Full-history raw command intervals; before source/hash-verified parent, after fresh; no IRQ/startup/reset',
        frames=10627,beforeBinarySha256=traces[0]['binarySha256'],afterBinarySha256=traces[1]['binarySha256'],groups=groups,speech=speech,streams=streams)


def record(args):
    assert args.corpus,'--record requires --corpus';reports=[]

    def retain(name,path,binary=None):
        data=json.loads(path.read_text())
        if binary:assert sha(binary,False)==data.get('binarySha256',data.get('input',{}).get('binarySha256'))
        name='zero-synthesis-'+name+'.json';save(name,data);reports.append(name)

    retain('baseline-source',OUT/'baseline-source.json')
    retain('identities',OUT/'identities.json')
    retain('export',ROOT/'build/low-export-check.json')
    retain('predicate',ROOT/'build/zero-vocoder-unit/predicate.json')
    retain('generic-unit',ROOT/'build/vocoder-unit/verification.json',ROOT/'build/vocoder-unit/unit.bin')
    for backend in ['asm','c']:
        folder=ROOT/'build/zero-vocoder-unit'/backend
        retain('unit-'+backend,folder/'verification.json',folder/'unit.bin')
        retain('unit-image-'+backend,folder/'input.json',folder/'unit.bin')
    retain('raw',OUT/'after/wb395/verification.json',OUT/'after/wb395/wb.bin')
    for name in ['irq8','irq11']:retain(name,OUT/'after'/name/'verification.json',OUT/'after'/name/'wb.bin')
    retain('spi',OUT/'after/spi/wb395/verification.json',OUT/'after/spi/wb395/player.bin')
    for epoch in ['before','after']:
        for label in ['nb','wb']:
            folder=OUT/epoch/'api'/label;retain(epoch+'-api-'+label,folder/'verification.json',folder/'api.bin')
    retain('streaming',ROOT/'build/noise-cache-unit/verification.json',ROOT/'build/noise-cache-unit/cache.bin')
    retain('feature',OUT/'features/asm/verification.json',OUT/'features/asm/wb.bin')
    name='zero-synthesis-timing.json';save(name,timing(args.corpus));reports.append(name)
    controls=dict(cDecoderExecuted=False,features=[],cImages=[])
    for backend in ['asm','c']:
        folder=OUT/'features'/backend;meta=json.loads((folder/'backend.json').read_text());binary=folder/'wb.bin'
        assert meta['backend']==backend and meta['lowRates']==4 and sha(binary,False)==meta['binarySha256']
        controls['features'].append(dict(backend=backend,lowRates=4,binarySha256=meta['binarySha256'],flashBytes=binary.stat().st_size,compileLinkedOnly=backend=='c'))
    folder=OUT/'c/wb395';meta=json.loads((folder/'input.json').read_text());binary=folder/'player.bin'
    assert meta['backend']=='c' and sha(binary,False)==meta['binarySha256']
    controls['cImages'].append(dict(profile='wb395',binarySha256=meta['binarySha256'],flashBytes=binary.stat().st_size,compileLinkedOnly=True))
    name='zero-synthesis-controls.json';save(name,controls);reports.append(name)
    base=read('nb1-zero-admission.json');sources=list(base['sourceSha256'])+ADDED;assert len(sources)==len(set(sources))
    save('zero-synthesis-admission.json',dict(baselineRevision='2e47ed00',baselineAdmissionSha256=sha(ROOT/'reports/nb1-zero-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',
        backend='Explicit AVR ASM with explicitly selectable equivalent C zero-vector primitive',physicalBoardTested=False,
        sourceSha256={n:sha(ROOT/n) for n in sources},reportSha256={n:sha(ROOT/'reports'/n) for n in reports},
        limits=['Fresh WB3.95: 10627 raw frames, 21254 IRQ frames at +8/+11%, 3600 continuous SPI frames.',
                'Before raw traces/output reports/images reused only after verifying parent sources, reports and image hashes.',
                'Eight rebuilt NB/no-NB1 images byte-identical; no fresh full other-mode timing claim.',
                'Only prepared contexts use the previous[0] predicate; general vector primitive keeps arbitrary tables.',
                'Zero primitive retains incoming pulse/noise on sample0, mean, phase, original noise and RNG work.',
                'Full C decoder/export compile/link only; isolated C vector controls execute.',
                'ISA simulation only; no board/analog measurements.']))


def audit(args):
    admission=read('zero-synthesis-admission.json');base=read('nb1-zero-admission.json')
    assert admission['baselineAdmissionSha256']==sha(ROOT/'reports/nb1-zero-admission.json')
    assert sorted(n for n,h in base['sourceSha256'].items() if sha(ROOT/n)!=h)==sorted(CHANGED)
    for n,h in admission['sourceSha256'].items():assert sha(ROOT/n)==h,n
    for n,h in {**base['reportSha256'],**admission['reportSha256']}.items():assert sha(ROOT/'reports'/n)==h,n
    for n,h in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==h,n
    b=read('zero-synthesis-baseline-source.json');assert b['sourceTreeVerified'] and b['sourceFiles']==len(base['sourceSha256']) and b['admissionSha256']==admission['baselineAdmissionSha256']
    predicate=read('zero-synthesis-predicate.json')
    assert predicate['preparedContextPredicateExact'] and not predicate['arbitraryContextPredicateClaimed']
    assert predicate['negativeNoiseGainPairs']==945344 and predicate['smallScaleGainPairs']==262208 and predicate['zeroBoundary']==4096
    assert predicate['packetScaleCodes']==32 and predicate['minimumPacketScale']==16384 and predicate['positiveGainZeroContextUnreachableForPackets']
    generic=read('zero-synthesis-generic-unit.json');assert generic['cases']==31540 and generic['pcmAndCursorExact'] and generic['calleeSavedAndR1Returns']==31540
    for backend in ['asm','c']:
        u=read('zero-synthesis-unit-'+backend+'.json');image=read('zero-synthesis-unit-image-'+backend+'.json')
        assert u['binarySha256']==image['binarySha256'] and u['backend']==image['backend']==backend
        assert u['cases']==33255 and u['pathsPerCase']==5 and u['pitchPhasePairs']==18432
        for k in ['fullSigned16CurrentSweep','incomingDifferenceOverflowEdges','originalTwoProductReference','wordsAndCursorExact','readOnlyInputsAndOutputBounds','explicitCSelectionVerified']:assert u[k],k
        assert u['calleeSavedAndR1Returns']==(99765 if backend=='asm' else 66510)
        assert u['pairedZeroMinusGeneralCycles']['max']<0 and u['removedPreviousAndPulseBytesPer40']==84
        s=u['stats'];assert s['general']['previousBytes']==33255*80 and s['general']['pulseBytes']==33255*4
        assert s['zero']['previousBytes']==s['zero']['pulseBytes']==0
        assert s['general']['muls']==s['general']['calls']*160 and s['zero']['muls']==s['zero']['calls']*160
    old=read('nb1-zero-after-wb395.json');new=read('zero-synthesis-raw.json');t=read('zero-synthesis-timing.json')
    assert old['binarySha256']==t['beforeBinarySha256'] and new['binarySha256']==t['afterBinarySha256']
    assert new['frames']==t['frames']==10627 and len(new['streams'])==18 and all(r['reset'] and r['pcmExact'] for r in new['streams'])
    assert new['flashBytes']==old['flashBytes']+188 and new['staticSramBytes']==old['staticSramBytes']==1284
    assert new['peakStack']==old['peakStack']==200 and new['freeSram']==old['freeSram']==564
    assert t['speech']['frames']==6467 and t['speech']['afterMeanCycles']<t['speech']['beforeMeanCycles']
    assert sum(r['frames'] for r in t['groups'].values())==10627 and t['groups']['zero']['deltaMax']<0
    for name,load in [('irq8',25600),('irq11',35200)]:
        old=read('nb1-zero-after-'+name+'.json');new=read('zero-synthesis-'+name+'.json')
        assert new['frames']==10627 and len(new['streams'])==18 and new['extraCpuCyclesPerFrame']==load and new['includesInterrupts'] and not new['underruns']
        for a,b in zip(old['streams'],new['streams']):
            for k in ['stream','frames','inputSha256','pcmSha256']:assert a[k]==b[k]
            assert b['s16AndPwmExact'] and b['fullHistoryWithoutChunkReset'] and not b['underruns']
            assert 990<=b['timerIntervalMinCycles']<=b['timerIntervalMaxCycles']<=1010
    old=read('nb1-zero-after-spi-wb395.json');new=read('zero-synthesis-spi.json')
    assert new['passed'] and new['frames']==3600 and new['s16Exact'] and new['pwmExact'] and not new['underruns']
    assert new['includesInterrupts'] and new['fullHistoryWithoutReset'] and new['input']['streamBytes']==new['modelStats']['readBytes']==36000
    for k in ['pcmSha256','pwmSha256','modelWasmSha256']:assert old[k]==new[k]
    for k in ['inputSha256','driverSha256']:assert old['input'][k]==new['input'][k]
    assert 990<=new['timerIntervalMinCycles']<=new['timerIntervalMaxCycles']<=1010
    expected={r['profile']:r['binarySha256'] for r in read('nb1-zero-controls.json')['images']}
    expected.update(nb215=read('nb1-zero-after-nb215.json')['binarySha256'])
    expected['spi-nb215']=read('nb1-zero-after-spi-nb215.json')['input']['binarySha256']
    identities=read('zero-synthesis-identities.json')['images'];assert len(identities)==8
    assert {r['profile'] for r in identities}==set(expected)
    for r in identities:assert r['byteIdentical'] and r['binarySha256']==expected[r['profile']]
    for label,rejected in [('nb',6144),('wb',7168)]:
        old,new=[read('zero-synthesis-'+e+'-api-'+label+'.json') for e in ['before','after']]
        original=json.loads(json.dumps(old))
        for k in ['zeroContextDispatchAvailable','byPath','preparedContextDispatchExact']:del original['vocoderArithmetic'][k]
        assert original==read('nb1-zero-after-api-'+label+'.json')
        for r in [old,new]:assert r['frames']==1024 and r['rejectedCalls']==rejected and r['pcmExact'] and r['resetExact'] and r['paddingIgnored']
        assert old['pcmSha256']==new['pcmSha256'] and old['inputSha256']==new['inputSha256']
        v=new['vocoderArithmetic'];assert v['zeroContextDispatchAvailable'] and v['preparedContextDispatchExact'] and v['calls']==824 and v['hardwareMultiplies']==131840
        assert sum(g['calls'] for g in v['byPath'].values())==824 and v['byPath']['zero']['calls']>=49*4 and v['byPath']['general']['calls']>0
        assert old['framePreparationArithmetic']==new['framePreparationArithmetic']
    s=read('zero-synthesis-streaming.json');assert s['frames']==1024 and s['cacheFrames']==205 and s['generatedBlocks']==s['foldedBlocks']==820
    assert s['generalVocoderCalls']+s['zeroVocoderCalls']==820 and s['zeroVocoderCalls']>=196
    for k in ['independentOriginalVocoder','allPartialStatesExact','classesAndSeedPerQuarterExact','readOnlyFoldWorkspace','outputAndScratchBounds','pcmExact','resetClearsWorkspace','preparationPreservesPersistentState','preparedContextDispatchExact']:assert s[k],k
    assert len(s['targetedZeroGainWithPriorPulse']['cases'])==4
    assert all(r['priorPulse']!=0 and r['independentExcitationAndQuarterStatesExact'] for r in s['targetedZeroGainWithPriorPulse']['cases'])
    positive=s['positiveGainZeroContext'];assert positive['packetScaleCodes']==32 and positive['minimumScale']==16384 and positive['unreachableForAllPacketScales']
    f=read('zero-synthesis-feature.json');assert f['frames']==384 and all(r['reset'] and r['pcmExact'] for r in f['streams'])
    controls=read('zero-synthesis-controls.json');assert not controls['cDecoderExecuted'] and len(controls['features'])==2
    assert all(r['lowRates']==4 and r['compileLinkedOnly']==(r['backend']=='c') for r in controls['features'])
    assert len(controls['cImages'])==1 and controls['cImages'][0]['compileLinkedOnly'] and controls['cImages'][0]['flashBytes']<=32768
    export=read('zero-synthesis-export.json');assert export['sources']==21 and not export['handwrittenAssembly'] and not export['duplicateSources']
    if args.corpus:
        assert timing(args.corpus)==t
        for row in read('low-final-corpus.json')['streams']:
            if row['profile']!='wb395':continue
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:assert sha(args.corpus/'wb395'/folder/(Path(row['stream']).stem+suffix),False)==row[key]
    print('PASS zero synthesis: 10627 fresh raw / 21254 loaded IRQ / 3600 SPI frames; exact PCM/PWM, vectors and quarter state')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record',action='store_true');parser.add_argument('--corpus',type=Path);args=parser.parse_args()
    if args.record:record(args)
    audit(args)


if __name__=='__main__':main()
