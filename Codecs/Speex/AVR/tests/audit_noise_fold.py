#!/usr/bin/env python3
"""Audit finite-alphabet folding, exact PCM and the admitted 8% IRQ gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
ADDED=['tests/avr_noise_fold.c','tests/build_noise_fold.py','tests/verify_noise_fold.mjs',
       'tests/build_noise_fold_admission.py','tests/run_noise_fold_admission.py','tests/audit_noise_fold.py',
       'tests/build_gain_admission.py','tests/run_gain_admission.py','tests/audit_gain_div.py']


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,value):
    (ROOT/'reports'/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())


def record():
    reports=[]
    def retain(name,path):
        save(name,json.loads(path.read_text()));reports.append(name)
    retain('noise-fold-unit.json',ROOT/'build/noise-fold-unit/verification.json')
    retain('noise-fold-screen.json',ROOT/'build/noise-fold-screen/verification.json')
    save('noise-fold-before-wb395.json',read('noise-shift-wb395.json'));reports.append('noise-fold-before-wb395.json')
    for label in ['wb395','irq8','spi','api/nb','api/wb']:
        retain('noise-fold-'+label.replace('/','-')+'.json',ROOT/'build/noise-fold-final'/label/'verification.json')
    retain('noise-fold-cache-pipeline.json',ROOT/'build/noise-cache-unit/verification.json')
    identities=[]
    for label in ['nb215','nb8','nb11','wb98','wb128']:
        binary='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[ROOT/'build/noise-fold-identities'/epoch/label/binary for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        identities.append(dict(profile=label,binarySha256=sha(paths[1],False),
                               flashBytes=paths[1].stat().st_size,byteIdentical=True))
    c_images=[]
    for label in ['nb11','wb395']:
        binary=ROOT/f'build/noise-fold-c/{label}/player.bin'
        meta=json.loads((binary.parent/'input.json').read_text())
        assert meta['backend']=='c' and meta['binarySha256']==sha(binary,False)
        c_images.append(dict(profile=label,binarySha256=sha(binary,False),
                             flashBytes=binary.stat().st_size,compiledLinkedOnly=True))
    save('noise-fold-identities.json',dict(images=identities,cImages=c_images,cDecoderExecuted=False))
    reports.append('noise-fold-identities.json')
    retain('noise-fold-export.json',ROOT/'build/low-export-check.json')
    fw=ROOT/'build/noise-fold-final/irq11';log=(fw/'run.log').read_text(encoding='utf-8')
    assert 'coverage4096.spxraw underruns' in log and 'PASS full history' not in log
    underruns=int(re.search(r'(\d+)\s*!==\s*0',log)[1]);assert underruns==8083
    save('noise-fold-irq11-rejected.json',dict(admitted=False,passed=False,
        firmware=json.loads((fw/'backend.json').read_text()),failedStream='coverage4096.spxraw',
        decoderFramesComparedBeforeFailure=4096,underruns=underruns,fullCorpusCompleted=False,
        pwmComparisonReached=False,includesInterrupts=True,physicalBoardTested=False,
        reason='Zero-underrun assertion failed after first stream; 11% is not an admitted gate.',
        localLogSha256=sha(fw/'run.log')))
    reports.append('noise-fold-irq11-rejected.json')
    base=read('noise-shift-admission.json');sources=list(base['sourceSha256'])+ADDED
    assert len(sources)==len(set(sources))
    save('noise-fold-admission.json',dict(baselineRevision='86ae0365',
        baselineAdmissionSha256=sha(ROOT/'reports/noise-shift-admission.json'),
        historicalGainAdmissionSha256=sha(ROOT/'reports/gain-div-admission.json'),
        target='ATmega328P / 16 MHz / 2 KB SRAM',backend='explicit AVR ASM',physicalBoardTested=False,
        sourceSha256={name:sha(ROOT/name) for name in sources},
        reportSha256={name:sha(ROOT/'reports'/name) for name in reports},
        admittedExtraCpuCyclesPerFrame=25600,
        limits=['Fresh complete decoder/IRQ/SPI runs cover affected WB3.95 only.',
                'NB2.15 and four minimum modes are rebuilt byte-identically; their prior evidence is retained.',
                'The extra 11% load fails with 8083 underruns on coverage; it is explicitly unadmitted.',
                'C decoder is compile/link only; explicit C arithmetic/lookup paths are tested.',
                'Existing compact Q7/16-tap QMF is unchanged; no physical-board/analog claim.']))


def audit(args):
    admission=read('noise-fold-admission.json');base=read('noise-shift-admission.json')
    assert sha(ROOT/'reports/noise-shift-admission.json')==admission['baselineAdmissionSha256']
    assert sha(ROOT/'reports/gain-div-admission.json')==admission['historicalGainAdmissionSha256']
    changed=sorted(name for name,value in base['sourceSha256'].items() if sha(ROOT/name)!=value)
    assert changed==sorted(['src/lowrate_noise.c','src/lowrate_noise.h','src/speex_wb1.c',
                            'src/wb_fold.c','src/wb_fold.h','src/wb_fold.S',
                            'tests/verify_low_api.mjs','tests/verify_noise_cache.mjs']),changed
    for name,value in admission['sourceSha256'].items():assert sha(ROOT/name)==value,name
    for name,value in admission['reportSha256'].items():assert sha(ROOT/'reports'/name)==value,name
    for name,value in read('spi-input-admission.json')['sourceSha256'].items():
        assert sha(ROOT.parents[2]/name)==value,name
    unit=read('noise-fold-unit.json')
    assert unit['cases']==88960 and unit['fivePathsExact'] and unit['fullSigned16SweepAtEveryTableSlot']
    assert unit['callerScales']==32 and unit['structuredGains']==183 and unit['allFourSubframes'] and unit['independentBigInt']
    assert unit['calleeSavedAndR1Returns']==3*unit['cases'] and unit['readonlyCache'] and unit['outputAndScratchGuards']
    assert unit['arbitraryNonArgumentRegisterPatterns'] and unit['argumentRegistersPreserved'] and unit['allLeafCalleeSavedRegisterPatterns']
    for label,muls in [('before',441),('after',56),('leaf',55)]:
        s=unit['asm'][label];assert s['calls']==unit['cases'] and s['muls']==muls*unit['cases']
    before=read('noise-fold-before-wb395.json');after=read('noise-fold-wb395.json')
    assert before==read('noise-shift-wb395.json')
    assert before['frames']==after['frames']==10627 and len(after['streams'])==18
    assert after['maxCycles']<before['maxCycles'] and after['meanCycles']<before['meanCycles']
    assert after['flashBytes']==before['flashBytes']+272 and after['staticSramBytes']==before['staticSramBytes']
    assert after['peakStack']==before['peakStack']+1
    for a,b in zip(after['streams'],before['streams']):
        assert a['name']==b['name'] and a['frames']==b['frames'] and a['pcmExact'] and a['reset']
        assert a['meanCycles']<b['meanCycles']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile']!='wb395':continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:
                assert sha(args.corpus/'wb395'/folder/(stem+suffix),False)==row[key]
    irq=read('noise-fold-irq8.json')
    assert irq['frames']==10627 and irq['includesInterrupts'] and irq['extraCpuCyclesPerFrame']==25600
    assert irq['underruns']==0 and irq['freeSramAtPeak']==410
    for row in irq['streams']:
        assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
        assert row['timerIntervalMinCycles']>=990 and row['timerIntervalMaxCycles']<=1010
    failure=read('noise-fold-irq11-rejected.json')
    assert not failure['admitted'] and not failure['passed'] and not failure['fullCorpusCompleted']
    assert failure['firmware']['frameLoadCycles']==35200 and failure['underruns']==8083
    spi=read('noise-fold-spi.json')
    assert spi['passed'] and spi['frames']==3600 and spi['input']['streamBytes']==36000
    assert spi['includesInterrupts'] and spi['s16Exact'] and spi['pwmExact'] and spi['underruns']==0
    assert spi['fullHistoryWithoutReset'] and spi['modelStats']['readBytes']==36000
    assert spi['pwmSha256']==read('noise-shift-spi.json')['pwmSha256']
    for label,rejects in [('nb',6144),('wb',7168)]:
        api=read('noise-fold-api-'+label+'.json')
        assert api['frames']==1024 and api['rejectedCalls']==rejects and api['pcmExact'] and api['resetExact']
        assert api['meanArithmetic']['calls']==32960 and api['noiseTableArithmetic']['calls']==206
        if label=='wb':
            f=api['noiseFoldArithmetic'];assert f['calls']==824 and f['hardwareMultiplies']==46144
            assert f['transformedValuesPerNb1Frame']==20 and f['foldMulsPerNb1Frame']==220 and f['controllerMulsPerNb1Frame']==224
            assert f['rejectedCallsDoNotExecute']
    identity=read('noise-fold-identities.json')
    pipeline=read('noise-fold-cache-pipeline.json')
    assert pipeline['frames']==1024 and pipeline['cacheFrames']==205 and pipeline['expandedBlocks']==820
    assert pipeline['calls']==dict(vocoder=205,values5=205,indices40=820,noiseFold40=820)
    assert pipeline['cacheBytes']==170 and pipeline['firstDelayedInputByte']==210 and pipeline['guardBytes']==40
    assert pipeline['nextHistorySourceByte']==320 and pipeline['cacheAndDelayedHistoryPreserved'] and pipeline['seedAdvancesOnce']
    assert pipeline['pcmExact'] and pipeline['resetClearsCache'] and pipeline['independentFoldFormula']
    assert pipeline['callerScratchWords']==5 and pipeline['callerScratchBoundsVerified']==820
    assert len(identity['images'])==5 and all(row['byteIdentical'] for row in identity['images'])
    assert identity['images'][0]['binarySha256']==read('noise-shift-nb215.json')['binarySha256']
    assert identity['cDecoderExecuted'] is False and len(identity['cImages'])==2
    assert all(row['compiledLinkedOnly'] and row['flashBytes']<=32768 for row in identity['cImages'])
    export=read('noise-fold-export.json');assert not export['handwrittenAssembly'] and not export['duplicateSources']
    print('PASS finite-alphabet fold: 88960 five-path cases / 10627 raw / 10627 IRQ +8% / 3600 SPI frames; +11% explicitly rejected')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true')
    p.add_argument('--corpus',type=Path,help='Optional lower-rate corpus for input/oracle hashes');args=p.parse_args()
    if args.record:record()
    audit(args)


if __name__=='__main__':main()
