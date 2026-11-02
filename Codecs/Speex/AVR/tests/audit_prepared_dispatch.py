#!/usr/bin/env python3
"""Bind prepared-dispatch ABI, exact PCM and continuous playback evidence."""
import argparse
import json
from pathlib import Path
from audit_nb1_gain import ROOT,sha,read,save
from audit_nb1_zero_synthesis import timing
OUT=ROOT/'build/prepared-final'
CHANGED=['src/lowrate_excitation.h','src/nb1_vocoder.h','src/nb1_vocoder.S','tests/avr_nb1_zero_vocoder.c',
         'tests/verify_nb1_zero_vocoder.mjs','tests/audit_nb1_zero_synthesis.py']
ADDED=['tests/build_prepared_dispatch.py','tests/run_prepared_dispatch.py','tests/audit_prepared_dispatch.py']


def record(args):
    assert args.corpus,'--record requires --corpus';reports=[]

    def retain(name,path,binary=None):
        data=json.loads(path.read_text())
        if binary:assert sha(binary,False)==data.get('binarySha256',data.get('input',{}).get('binarySha256'))
        name='prepared-'+name+'.json';save(name,data);reports.append(name)

    retain('baseline-source',OUT/'baseline-source.json');retain('identities',OUT/'identities.json')
    retain('export',ROOT/'build/low-export-check.json')
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
    name='prepared-timing.json';save(name,timing(args.corpus,out=OUT));reports.append(name)
    controls=dict(cDecoderExecuted=False,features=[],cImages=[])
    for backend in ['asm','c']:
        folder=OUT/'features'/backend;meta=json.loads((folder/'backend.json').read_text());binary=folder/'wb.bin'
        assert meta['backend']==backend and meta['lowRates']==4 and sha(binary,False)==meta['binarySha256']
        controls['features'].append(dict(backend=backend,lowRates=4,binarySha256=meta['binarySha256'],flashBytes=binary.stat().st_size,compileLinkedOnly=backend=='c'))
    folder=OUT/'c/wb395';meta=json.loads((folder/'input.json').read_text());binary=folder/'player.bin'
    assert meta['backend']=='c' and sha(binary,False)==meta['binarySha256']
    controls['cImages'].append(dict(profile='wb395',binarySha256=meta['binarySha256'],flashBytes=binary.stat().st_size,compileLinkedOnly=True))
    name='prepared-controls.json';save(name,controls);reports.append(name)
    base=read('zero-synthesis-admission.json');sources=list(base['sourceSha256'])+ADDED
    assert len(sources)==len(set(sources))
    save('prepared-admission.json',dict(baselineRevision='0e8776be',baselineAdmissionSha256=sha(ROOT/'reports/zero-synthesis-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues, mrelax',
        backend='Explicit AVR ASM prepared entry; explicitly selectable equivalent C dispatcher',physicalBoardTested=False,
        sourceSha256={n:sha(ROOT/n) for n in sources},reportSha256={n:sha(ROOT/'reports'/n) for n in reports},
        limits=['Fresh after: 10627 WB3.95 raw, 21254 IRQ at +8/+11%, 3600 continuous SPI frames.',
                'Parent raw/IRQ/SPI reports/images are reused after source/report/image verification; before APIs are freshly observed.',
                'Only prepared-context dispatch moves; both synthesis bodies, original mean/noise/RNG/QMF remain unchanged.',
                'Eight NB/no-NB1 images and both full C controls retain byte identity; no fresh all-feature other-mode timing claim.',
                'Full C decoder/export compile/link only; isolated C vector/dispatch controls execute.',
                'ISA simulation only, not physical-board or analog measurements.']))


def audit(args):
    admission=read('prepared-admission.json');base=read('zero-synthesis-admission.json')
    assert admission['baselineAdmissionSha256']==sha(ROOT/'reports/zero-synthesis-admission.json')
    assert sorted(n for n,h in base['sourceSha256'].items() if sha(ROOT/n)!=h)==sorted(CHANGED)
    for n,h in admission['sourceSha256'].items():assert sha(ROOT/n)==h,n
    for n,h in {**base['reportSha256'],**admission['reportSha256']}.items():assert sha(ROOT/'reports'/n)==h,n
    for n,h in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==h,n
    b=read('prepared-baseline-source.json');assert b['sourceTreeVerified'] and b['sourceFiles']==len(base['sourceSha256']) and b['admissionSha256']==admission['baselineAdmissionSha256']
    for backend in ['asm','c']:
        u=read('prepared-unit-'+backend+'.json');image=read('prepared-unit-image-'+backend+'.json')
        assert u['backend']==image['backend']==backend and u['binarySha256']==image['binarySha256']
        assert (u['cases'],u['zeroCases'],u['ordinaryCases'])==(98791,33256,65535)
        for k in ['fullSigned16CurrentSweep','incomingDifferenceOverflowEdges','fullSigned16PredicateSweep','preparedEntryTailBranchAndArgumentsExact',
                  'originalTwoProductReference','wordsAndCursorExact','readOnlyInputsAndOutputBounds','explicitCSelectionVerified']:assert u[k],k
        assert u['calleeSavedAndR1Returns']==(230838 if backend=='asm' else 132047)
        s=u['stats'];assert s['general']['calls']==98791 and s['zero']['calls']==33256 and s['prepared']['calls']==(98791 if backend=='asm' else 0)
        assert all(r['muls']==160*r['calls'] for r in s.values())
        if backend=='asm':assert s['prepared']['previousBytes']==98791*2+65535*80 and s['prepared']['pulseBytes']==65535*4
    old=read('zero-synthesis-raw.json');new=read('prepared-raw.json');t=read('prepared-timing.json')
    assert old['binarySha256']==t['beforeBinarySha256'] and new['binarySha256']==t['afterBinarySha256']
    assert new['frames']==t['frames']==10627 and len(new['streams'])==18 and all(r['reset'] and r['pcmExact'] for r in new['streams'])
    assert new['flashBytes']==old['flashBytes']-18 and new['staticSramBytes']==old['staticSramBytes']==1284
    assert new['peakStack']==old['peakStack']==200 and new['freeSram']==old['freeSram']==564
    assert t['speech']['frames']==6467 and t['speech']['afterMeanCycles']<t['speech']['beforeMeanCycles']
    assert sum(g['frames'] for g in t['groups'].values())==10627
    assert (t['groups']['zero']['deltaMin'],t['groups']['zero']['deltaMax'])==(-60,-60)
    assert (t['groups']['ordinary']['deltaMin'],t['groups']['ordinary']['deltaMax'])==(-52,-52)
    for name,load in [('irq8',25600),('irq11',35200)]:
        old=read('zero-synthesis-'+name+'.json');new=read('prepared-'+name+'.json')
        assert new['frames']==10627 and len(new['streams'])==18 and new['extraCpuCyclesPerFrame']==load and new['includesInterrupts'] and not new['underruns']
        for a,b in zip(old['streams'],new['streams']):
            for k in ['stream','frames','inputSha256','pcmSha256']:assert a[k]==b[k]
            assert b['s16AndPwmExact'] and b['fullHistoryWithoutChunkReset'] and not b['underruns'] and 990<=b['timerIntervalMinCycles']<=b['timerIntervalMaxCycles']<=1010
    old=read('zero-synthesis-spi.json');new=read('prepared-spi.json')
    assert new['passed'] and new['frames']==3600 and new['s16Exact'] and new['pwmExact'] and not new['underruns'] and new['includesInterrupts'] and new['fullHistoryWithoutReset']
    assert new['input']['streamBytes']==new['modelStats']['readBytes']==36000 and 990<=new['timerIntervalMinCycles']<=new['timerIntervalMaxCycles']<=1010
    for k in ['pcmSha256','pwmSha256','modelWasmSha256']:assert old[k]==new[k]
    for k in ['inputSha256','driverSha256']:assert old['input'][k]==new['input'][k]
    assert read('prepared-identities.json')==read('zero-synthesis-identities.json')
    for label,rejected in [('nb',6144),('wb',7168)]:
        old,new=[read('prepared-'+e+'-api-'+label+'.json') for e in ['before','after']]
        assert old==read('zero-synthesis-after-api-'+label+'.json')
        for r in [old,new]:assert r['frames']==1024 and r['rejectedCalls']==rejected and r['pcmExact'] and r['resetExact'] and r['paddingIgnored']
        for k in ['inputSha256','pcmSha256','vocoderArithmetic','framePreparationArithmetic','nb1GainLookup','noiseTableArithmetic']:assert old[k]==new[k]
    old=read('zero-synthesis-streaming.json');new=read('prepared-streaming.json')
    for k in ['frames','cacheFrames','generatedBlocks','foldedBlocks','valuesCalls','indicesCalls','generalVocoderCalls','zeroVocoderCalls','pcmSha256',
              'allPartialStatesExact','classesAndSeedPerQuarterExact','readOnlyFoldWorkspace','outputAndScratchBounds','pcmExact','resetClearsWorkspace',
              'preparationPreservesPersistentState','preparedContextDispatchExact','targetedZeroGainWithPriorPulse','positiveGainZeroContext']:assert old[k]==new[k],k
    f=read('prepared-feature.json');assert f['frames']==384 and all(r['reset'] and r['pcmExact'] for r in f['streams'])
    controls=read('prepared-controls.json');parent=read('zero-synthesis-controls.json');assert not controls['cDecoderExecuted']
    assert next(r for r in controls['features'] if r['backend']=='c')==next(r for r in parent['features'] if r['backend']=='c')
    assert controls['cImages']==parent['cImages'] and all(r['compileLinkedOnly'] for r in controls['cImages'])
    export=read('prepared-export.json');assert export['sources']==21 and not export['handwrittenAssembly'] and not export['duplicateSources']
    if args.corpus:
        assert timing(args.corpus,out=OUT)==t
        for row in read('low-final-corpus.json')['streams']:
            if row['profile']!='wb395':continue
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:assert sha(args.corpus/'wb395'/folder/(Path(row['stream']).stem+suffix),False)==row[key]
    print('PASS prepared dispatch: all 10627 frames faster; loaded IRQ/SPI exact without underruns; equivalent selectable C vectors')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--record',action='store_true');parser.add_argument('--corpus',type=Path);args=parser.parse_args()
    if args.record:record(args)
    audit(args)


if __name__=='__main__':main()
