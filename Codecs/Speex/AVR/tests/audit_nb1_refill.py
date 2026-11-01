#!/usr/bin/env python3
"""Bind exact NB1 quarter synthesis, arithmetic, complete output and C controls."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ADDED=['src/nb1_cache_layout.h','src/lowrate_mean_kernel.inc','src/nb1_vocoder.h',
       'src/nb1_vocoder.c','src/nb1_vocoder.S','tests/avr_nb1_vocoder.c',
       'tests/build_nb1_vocoder.py','tests/verify_nb1_vocoder.mjs',
       'tests/verify_nb1_streaming.mjs','tests/build_nb1_refill_admission.py',
       'tests/run_nb1_refill_admission.py','tests/check_refill_c_export.py','tests/audit_nb1_refill.py']
CHANGED=['src/lowrate_excitation.h','src/lowrate_noise.h','src/lowrate_mean.S',
         'src/nb_decode.c.inc','tools/build_wb.py','tests/avr_noise_cache.c',
         'tests/verify_low_api.mjs','tests/verify_wb_stream.mjs']


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,value):(ROOT/'reports'/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())


def record():
    reports=[]

    def retain(label,path):
        name='nb1-refill-'+label+'.json';save(name,json.loads(path.read_text()));reports.append(name)

    for label,path in [('vocoder-unit','vocoder-unit/verification.json'),('mean-unit','mean-unit/verification.json'),
                       ('streaming','noise-cache-unit/verification.json'),('screen','refill-fused-screen/verification.json'),
                       ('c-controller-rejected','refill-screen/verification.json'),('export','low-export-check.json')]:
        retain(label,ROOT/'build'/path)
    for epoch in ['before','after']:
        retain('gap-screen-'+epoch,ROOT/'build/nb1-refill-gap-screen'/epoch/'verification.json')
    for label in ['wb395','irq8','irq11','spi','api/nb','api/wb']:
        retain(label.replace('/','-'),ROOT/'build/nb1-refill-final'/label/'verification.json')
    retain('nb215',ROOT/'build/nb1-refill-final/nb215/avr-verification.json')
    for label,source in [('wb395','noise-fold-wb395.json'),('nb215','noise-shift-nb215.json')]:
        name='nb1-refill-before-'+label+'.json';save(name,read(source));reports.append(name)
    identities=[]
    for label in ['nb8','nb11','wb98','wb128']:
        filename='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[ROOT/'build/nb1-refill-identities'/epoch/label/filename for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        identities.append(dict(profile=label,binarySha256=sha(paths[1],False),flashBytes=paths[1].stat().st_size,byteIdentical=True))
    c_images=[]
    for label in ['nb11','wb395']:
        binary=ROOT/f'build/nb1-refill-c/{label}/player.bin';meta=json.loads((binary.parent/'input.json').read_text())
        assert meta['backend']=='c' and meta['binarySha256']==sha(binary,False)
        c_images.append(dict(profile=label,binarySha256=meta['binarySha256'],flashBytes=binary.stat().st_size,compiledLinkedOnly=True))
    name='nb1-refill-controls.json';save(name,dict(images=identities,cImages=c_images,cDecoderExecuted=False));reports.append(name)
    base=read('noise-fold-admission.json');sources=list(base['sourceSha256'])+ADDED
    assert len(sources)==len(set(sources))
    save('nb1-refill-admission.json',dict(baselineRevision='ab597728',
        baselineAdmissionSha256=sha(ROOT/'reports/noise-fold-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',backend='explicit AVR ASM',
        compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',
        physicalBoardTested=False,sourceSha256={name:sha(ROOT/name) for name in sources},
        reportSha256={name:sha(ROOT/'reports'/name) for name in reports},
        admittedExtraCpuCyclesPerFrame=35200,
        limits=['Fresh full decoder runs cover NB2.15 and WB3.95; active IRQ/SPI runs cover WB3.95.',
                'Four minimum-mode images are rebuilt byte-identically; their prior evidence is retained.',
                'C decoder is compile/link only; isolated explicit C scalar/vector primitives are executed.',
                'The slower C quarter-controller experiment is rejected; the fused ASM candidate is measured separately.',
                'Compact Q7/16-tap QMF and all arithmetic quantizers are unchanged; no physical-board or analog claim.']))


def audit(args):
    admission=read('nb1-refill-admission.json');base=read('noise-fold-admission.json')
    assert sha(ROOT/'reports/noise-fold-admission.json')==admission['baselineAdmissionSha256']
    changed=sorted(name for name,value in base['sourceSha256'].items() if sha(ROOT/name)!=value)
    assert changed==sorted(CHANGED),changed
    for name,value in admission['sourceSha256'].items():assert sha(ROOT/name)==value,name
    for name,value in admission['reportSha256'].items():assert sha(ROOT/'reports'/name)==value,name
    for name,value in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/name)==value,name
    unit=read('nb1-refill-vocoder-unit.json')
    assert unit['cases']==31540 and unit['pcmAndCursorExact'] and unit['originalTwoProductBigIntReference']
    assert unit['completeSignedWordTableSweep'] and unit['pitchPhasePairs']==18432 and unit['readOnlyInputsAndOutputBounds']
    assert unit['calleeSavedAndR1Returns']==unit['cases'] and unit['arbitraryRegisterPatterns'] and unit['hardwareMultipliesPer40']==160
    mean=read('nb1-refill-mean-unit.json')
    assert mean['cases']==1212335 and mean['cAndAsmExact'] and mean['calleeSavedAndR1Returns']==mean['cases']
    assert mean['hardwareMultipliesPerCall']==4 and mean['asmFunctionMinCycles']==42 and mean['asmFunctionMaxCycles']==47
    pipe=read('nb1-refill-streaming.json')
    assert pipe['frames']==1024 and pipe['cacheFrames']==205 and pipe['generatedBlocks']==pipe['foldedBlocks']==820
    assert pipe['valuesCalls']==205 and pipe['indicesCalls']==820 and pipe['reusedWorkspaceBytes']==198 and pipe['guardBytes']==12
    for key in ['independentOriginalVocoder','allPartialStatesExact','classesAndSeedPerQuarterExact','readOnlyFoldWorkspace',
                'outputAndScratchBounds','pcmExact','resetClearsWorkspace']:assert pipe[key],key
    before=read('nb1-refill-before-wb395.json');after=read('nb1-refill-wb395.json')
    assert before==read('noise-fold-wb395.json') and after['frames']==before['frames']==10627
    assert len(after['streams'])==18 and after['meanCycles']<before['meanCycles'] and after['maxCycles']<before['maxCycles']
    assert after['flashBytes']==before['flashBytes']+286 and after['staticSramBytes']==before['staticSramBytes']
    assert after['peakStack']==before['peakStack'] and after['freeSram']==before['freeSram']
    for a,b in zip(after['streams'],before['streams']):
        assert a['name']==b['name'] and a['frames']==b['frames'] and a['reset'] and a['pcmExact'] and a['meanCycles']<b['meanCycles']
    nb=read('nb1-refill-nb215.json');nb_before=read('nb1-refill-before-nb215.json')
    assert nb_before==read('noise-shift-nb215.json') and nb['frames']==10627 and len(nb['streams'])==18
    assert nb['flashBytes']==nb_before['flashBytes']-2 and nb['staticSramBytes']==nb_before['staticSramBytes']
    for a,b in zip(nb['streams'],nb_before['streams']):
        assert a['stream']==b['stream'] and a['frames']==b['frames'] and a['resetVerified']
        assert a['meanCycles']==b['meanCycles']-160 and a['stackBytes']==b['stackBytes']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile'] not in ['nb215','wb395']:continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:
                assert sha(args.corpus/row['profile']/folder/(stem+suffix),False)==row[key]
    for label,load in [('irq8',25600),('irq11',35200)]:
        irq=read('nb1-refill-'+label+'.json')
        assert irq['frames']==10627 and irq['includesInterrupts'] and irq['extraCpuCyclesPerFrame']==load and irq['underruns']==0
        for row in irq['streams']:
            assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
            assert 990<=row['timerIntervalMinCycles']<=row['timerIntervalMaxCycles']<=1010
            assert row['refillPublications']==4*row['frames'] and row['minQueueImmediatelyBeforeRefill']>0
    spi=read('nb1-refill-spi.json')
    assert spi['passed'] and spi['frames']==3600 and spi['input']['streamBytes']==36000 and spi['modelStats']['readBytes']==36000
    assert spi['includesInterrupts'] and spi['s16Exact'] and spi['pwmExact'] and spi['underruns']==0 and spi['fullHistoryWithoutReset']
    assert spi['pwmSha256']==read('noise-fold-spi.json')['pwmSha256']
    for label,rejects in [('nb',6144),('wb',7168)]:
        api=read('nb1-refill-api-'+label+'.json')
        assert api['frames']==1024 and api['rejectedCalls']==rejects and api['pcmExact'] and api['resetExact']
        assert api['vocoderArithmetic']['calls']==824 and api['vocoderArithmetic']['hardwareMultiplies']==131840
        assert api['vocoderArithmetic']['rejectedCallsDoNotExecute'] and api['noiseTableArithmetic']['calls']==206
        if label=='wb':assert api['noiseFoldArithmetic']['calls']==824 and api['noiseFoldArithmetic']['hardwareMultiplies']==46144
    controls=read('nb1-refill-controls.json')
    assert len(controls['images'])==4 and all(r['byteIdentical'] for r in controls['images'])
    assert controls['cDecoderExecuted'] is False and len(controls['cImages'])==2
    assert all(r['compiledLinkedOnly'] and r['flashBytes']<=32768 for r in controls['cImages'])
    export=read('nb1-refill-export.json');assert export['sources']==21 and not export['handwrittenAssembly'] and not export['duplicateSources']
    rejected=read('nb1-refill-c-controller-rejected.json');screen=read('nb1-refill-screen.json')
    assert rejected['frames']==screen['frames']==384 and rejected['meanCycles']>screen['meanCycles']
    for epoch in ['before','after']:
        gap=read('nb1-refill-gap-screen-'+epoch+'.json')
        assert gap['frames']==384 and gap['includesInterrupts'] and gap['extraCpuCyclesPerFrame']==25600 and gap['underruns']==0
    a=read('nb1-refill-gap-screen-after.json');b=read('nb1-refill-gap-screen-before.json')
    for new,old in zip(a['streams'],b['streams']):
        assert new['stream']==old['stream'] and new['inputSha256']==old['inputSha256'] and new['pcmSha256']==old['pcmSha256']
        assert new['maxFrameBoundaryRefillGapCycles']<old['maxFrameBoundaryRefillGapCycles']
    print('PASS exact NB1 refill: 31540 vector / 1212335 mean cases; 21254 raw / 21254 IRQ / 3600 SPI frames; +11% admitted')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');p.add_argument('--corpus',type=Path)
    args=p.parse_args()
    if args.record:record()
    audit(args)


if __name__=='__main__':main()
