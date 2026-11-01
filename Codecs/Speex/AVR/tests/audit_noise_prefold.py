#!/usr/bin/env python3
"""Bind exact frame-invariant Q15 and zero-class elimination to full output."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHANGED=['src/lowrate_excitation.h','src/nb1_cache_layout.h','src/wb_fold.c','src/wb_fold.h','src/wb_fold.S',
         'tests/avr_noise_fold.c','tests/verify_noise_fold.mjs','tests/verify_low_api.mjs','tests/verify_nb1_streaming.mjs']
ADDED=['tests/build_noise_prefold_admission.py','tests/run_noise_prefold_admission.py','tests/audit_noise_prefold.py']


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,data):(ROOT/'reports'/name).write_bytes((json.dumps(data,indent=2)+'\n').encode())


def record():
    reports=[]

    def retain(label,path):
        name='noise-prefold-'+label+'.json';save(name,json.loads(path.read_text()));reports.append(name)

    for label,path in [('unit','noise-fold-unit/verification.json'),('screen','q15-final-screen/verification.json'),
                       ('simple-screen','q15-simple-screen.json'),('compressed-rejected','q15-compressed-screen.json'),
                       ('streaming','noise-cache-unit/verification.json'),('export','low-export-check.json'),
                       ('before-api','noise-prefold-before-api/verification.json')]:retain(label,ROOT/'build'/path)
    for label in ['wb395','irq8','irq11','spi','api/nb','api/wb']:
        retain(label.replace('/','-'),ROOT/'build/noise-prefold-final'/label/'verification.json')
    images=[]
    for label in ['nb215','nb8','nb11','wb98','wb128']:
        filename='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[ROOT/'build/noise-prefold-identities'/epoch/label/filename for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,binarySha256=sha(paths[1],False),flashBytes=paths[1].stat().st_size,byteIdentical=True))
    c_images=[]
    for label in ['nb11','wb395']:
        binary=ROOT/f'build/noise-prefold-c/{label}/player.bin';meta=json.loads((binary.parent/'input.json').read_text())
        assert meta['backend']=='c' and meta['binarySha256']==sha(binary,False)
        c_images.append(dict(profile=label,binarySha256=meta['binarySha256'],flashBytes=binary.stat().st_size,compiledLinkedOnly=True))
    name='noise-prefold-controls.json';save(name,dict(images=images,cImages=c_images,cDecoderExecuted=False));reports.append(name)
    base=read('nb1-refill-admission.json');sources=list(base['sourceSha256'])+ADDED;assert len(sources)==len(set(sources))
    save('noise-prefold-admission.json',dict(baselineRevision='56ffaa45',
        baselineAdmissionSha256=sha(ROOT/'reports/nb1-refill-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',backend='explicit AVR ASM',
        compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',physicalBoardTested=False,
        sourceSha256={name:sha(ROOT/name) for name in sources},reportSha256={name:sha(ROOT/'reports'/name) for name in reports},
        admittedExtraCpuCyclesPerFrame=35200,
        limits=['Fresh full decoder and IRQ/SPI runs cover affected WB3.95 only.',
                'Five other profile images are rebuilt byte-identically; their prior evidence is retained.',
                'Two APIs in WB-enabled builds execute the new preparation; a matched before/after MUL observer covers this.',
                'C decoder is compile/link only; isolated C arithmetic/lookup paths are tested.',
                'The compressed four-word variant is rejected; measured screens are retained separately.',
                'Compact Q7/16-tap QMF and all quantizers remain unchanged; no physical-board or analog claim.']))


def audit(args):
    a=read('noise-prefold-admission.json');base=read('nb1-refill-admission.json')
    assert sha(ROOT/'reports/nb1-refill-admission.json')==a['baselineAdmissionSha256']
    assert sorted(n for n,v in base['sourceSha256'].items() if sha(ROOT/n)!=v)==sorted(CHANGED)
    for n,v in a['sourceSha256'].items():assert sha(ROOT/n)==v,n
    for n,v in {**base['reportSha256'],**a['reportSha256']}.items():assert sha(ROOT/'reports'/n)==v,n
    for n,v in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==v,n
    u=read('noise-prefold-unit.json')
    assert u['cases']==88960 and u['sevenPathsExact'] and u['fullSigned16SweepAtNonzeroClassSlots'] and u['zeroClass2']
    assert u['callerScales']==32 and u['structuredGains']==183 and u['allFourSubframes'] and u['independentBigInt']
    assert u['calleeSavedAndR1Returns']==4*u['cases'] and u['readonlyWorkspaceBytes']==208 and u['readonlyCache'] and u['outputAndScratchGuards']
    assert u['arbitraryNonArgumentRegisterPatterns'] and u['argumentRegistersPreserved'] and u['allLeafCalleeSavedRegisterPatterns']
    for label,muls in [('before',441),('after',29),('leaf',55),('scaleLeaf',28)]:
        s=u['asm'][label];assert s['calls']==u['cases'] and s['muls']==u['cases']*muls
    before=read('nb1-refill-wb395.json');after=read('noise-prefold-wb395.json')
    assert before['frames']==after['frames']==10627 and len(after['streams'])==18
    assert after['flashBytes']==before['flashBytes']-4 and after['staticSramBytes']==before['staticSramBytes']
    assert after['peakStack']==before['peakStack'] and after['freeSram']==before['freeSram']
    for x,y in zip(after['streams'],before['streams']):
        assert x['name']==y['name'] and x['frames']==y['frames'] and x['reset'] and x['pcmExact']
        assert x['meanCycles']==y['meanCycles']-343 and x['maxCycles']==y['maxCycles']-343
    assert abs((before['meanCycles']-after['meanCycles'])-343)<1e-8
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile']!='wb395':continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:
                assert sha(args.corpus/'wb395'/folder/(stem+suffix),False)==row[key]
    for label,load in [('irq8',25600),('irq11',35200)]:
        irq=read('noise-prefold-'+label+'.json')
        previous=read('nb1-refill-'+label+'.json')
        assert irq['frames']==10627 and irq['includesInterrupts'] and irq['extraCpuCyclesPerFrame']==load and irq['underruns']==0
        assert irq['minQueuedSamplesBeforeOutput']==previous['minQueuedSamplesBeforeOutput']
        assert max(r['maxFrameBoundaryRefillGapCycles'] for r in irq['streams'])==113+max(r['maxFrameBoundaryRefillGapCycles'] for r in previous['streams'])
        assert max(r['maxIntraFrameRefillGapCycles'] for r in irq['streams'])==max(r['maxIntraFrameRefillGapCycles'] for r in previous['streams'])
        for row in irq['streams']:
            assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
            assert 990<=row['timerIntervalMinCycles']<=row['timerIntervalMaxCycles']<=1010
            assert row['refillPublications']==4*row['frames'] and row['minQueueImmediatelyBeforeRefill']>0
    spi=read('noise-prefold-spi.json')
    assert spi['passed'] and spi['frames']==3600 and spi['input']['streamBytes']==spi['modelStats']['readBytes']==36000
    assert spi['includesInterrupts'] and spi['s16Exact'] and spi['pwmExact'] and spi['underruns']==0 and spi['fullHistoryWithoutReset']
    assert spi['pwmSha256']==read('nb1-refill-spi.json')['pwmSha256']
    old_api=read('noise-prefold-before-api.json')
    assert old_api['binarySha256']==read('nb1-refill-api-wb.json')['binarySha256']
    for label,rejects in [('nb',6144),('wb',7168)]:
        api=read('noise-prefold-api-'+label+'.json')
        assert api['frames']==1024 and api['rejectedCalls']==rejects and api['pcmExact'] and api['resetExact']
        assert api['vocoderArithmetic']['calls']==824 and api['vocoderArithmetic']['hardwareMultiplies']==131840
        assert api['noiseTableArithmetic']['calls']==206
        p=api['framePreparationArithmetic'];q=old_api['framePreparationArithmetic']
        assert p['calls']==q['calls']==206 and p['rejectedCallsDoNotExecute'] and q['rejectedCallsDoNotExecute']
        assert len(p['perCall'])==len(q['perCall'])==206 and all(x-y==16 for x,y in zip(p['perCall'],q['perCall']))
        if label=='wb':
            fold=api['noiseFoldArithmetic'];assert fold['calls']==824 and fold['hardwareMultiplies']==824*29
            assert read('nb1-refill-api-wb.json')['noiseFoldArithmetic']['hardwareMultiplies']+q['hardwareMultiplies']-fold['hardwareMultiplies']-p['hardwareMultiplies']==92*206
    p=read('noise-prefold-streaming.json')
    assert p['frames']==1024 and p['cacheFrames']==205 and p['generatedBlocks']==p['foldedBlocks']==820
    assert p['prefoldBytes']==10 and p['reusedWorkspaceBytes']==208 and p['guardBytes']==2
    for key in ['independentOriginalVocoder','allPartialStatesExact','classesAndSeedPerQuarterExact','readOnlyFoldWorkspace',
                'outputAndScratchBounds','pcmExact','resetClearsWorkspace']:assert p[key],key
    c=read('noise-prefold-controls.json')
    assert len(c['images'])==5 and all(i['byteIdentical'] for i in c['images']) and not c['cDecoderExecuted']
    assert c['images'][0]['binarySha256']==read('nb1-refill-nb215.json')['binarySha256']
    assert len(c['cImages'])==2 and all(i['compiledLinkedOnly'] and i['flashBytes']<=32768 for i in c['cImages'])
    export=read('noise-prefold-export.json');assert export['sources']==21 and not export['handwrittenAssembly'] and not export['duplicateSources']
    final=read('noise-prefold-screen.json');simple=read('noise-prefold-simple-screen.json');rejected=read('noise-prefold-compressed-rejected.json')
    assert final['frames']==simple['frames']==rejected['frames']==384
    assert final['meanCycles']<simple['meanCycles']<rejected['meanCycles'] and final['flashBytes']<simple['flashBytes']<rejected['flashBytes']
    print('PASS exact noise prefold: 88960 seven-path cases / 10627 raw / 21254 IRQ / 3600 SPI frames; 92 MULs and 343 cycles saved/frame')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');p.add_argument('--corpus',type=Path)
    args=p.parse_args()
    if args.record:record()
    audit(args)


if __name__=='__main__':main()
