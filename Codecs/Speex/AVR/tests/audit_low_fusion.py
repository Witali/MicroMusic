#!/usr/bin/env python3
"""Bind exact WB5.75/WB7.75 fusion, memory traffic and full output admission."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHANGED=['src/wb_fold.c','src/wb_fold.h','src/wb_fold.S','tests/verify_low_api.mjs']
ADDED=['tests/avr_low_fusion.c','tests/build_low_fusion.py','tests/verify_low_fusion.mjs',
       'tests/build_low_fusion_admission.py','tests/run_low_fusion_admission.py','tests/audit_low_fusion.py']
PROFILES={'wb575':(15,3252),'wb775':(20,3428)}


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,data):(ROOT/'reports'/name).write_bytes((json.dumps(data,indent=2)+'\n').encode())


def record():
    reports=[];out=ROOT/'build/low-fusion-final'

    def retain(label,path):
        name='low-fusion-'+label+'.json';save(name,json.loads(path.read_text()));reports.append(name)

    retain('unit',ROOT/'build/low-fusion-unit/verification.json')
    retain('baseline-source',out/'baseline-source.json')
    retain('screen-corpus',ROOT/'build/low-fuse-screen-data/manifest.json')
    retain('export',ROOT/'build/low-export-check.json')
    for label in PROFILES:
        for phase in ['before','after','irq','spi']:
            retain(phase+'-'+label,out/phase/label/'verification.json')
        retain('feature-'+label,out/'features/asm'/label/'verification.json')
        for name,path in [('screen-before',ROOT/'build/low-fuse-screen/before'),
                          ('outlined-screen',ROOT/'build/low-fuse-outlined-screen'),
                          ('screen-after',ROOT/'build/low-fuse-inline-screen')]:
            retain(name+'-'+label,path/label/'verification.json')
    for label in ['nb','wb']:retain('api-'+label,out/'api'/label/'verification.json')
    production=[]
    for label in PROFILES:
        symbols=(out/'after'/label/'symbols.txt').read_text()
        assert 'speex_wb_fold40_avr' not in symbols and 'speex_wb_excitation_low40' not in symbols
        assert all('speex_wb_excitation_nb'+str(m)+'_40_avr' in symbols for m in [2,8])
        production.append(dict(profile=label,oldFoldAndControllerAbsent=True,newLeavesPresent=True,inlineDispatcherAbsent=True))
    images=[]
    for label in ['nb215','nb8','nb11','wb98','wb128']:
        name='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[out/'identities'/epoch/label/name for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,binarySha256=sha(paths[1],False),flashBytes=paths[1].stat().st_size,byteIdentical=True))
    features=[]
    for label in PROFILES:
        for backend in ['asm','c']:
            path=out/'features'/backend/label;meta=json.loads((path/'backend.json').read_text());symbols=(path/'symbols.txt').read_text()
            assert sha(path/'wb.bin',False)==meta['binarySha256'] and meta['lowRates']==(2 if label=='wb575' else 1)
            own='speex_wb_excitation_nb'+('8' if label=='wb575' else '2')+'_40_avr'
            other='speex_wb_excitation_nb'+('2' if label=='wb575' else '8')+'_40_avr'
            assert other not in symbols and (own in symbols)==(backend=='asm')
            if backend=='c':assert 'speex_wb_excitation_low40_c' in symbols
            features.append(dict(profile=label,backend=backend,lowRates=meta['lowRates'],binarySha256=meta['binarySha256'],
                flashBytes=(path/'wb.bin').stat().st_size,unusedKernelAbsent=True,selectedKernelPresent=backend=='asm',
                compiledLinkedOnly=backend=='c'))
    c_images=[]
    for label in PROFILES:
        path=out/'c'/label;meta=json.loads((path/'input.json').read_text());assert meta['backend']=='c'
        assert sha(path/'player.bin',False)==meta['binarySha256']
        c_images.append(dict(profile=label,binarySha256=meta['binarySha256'],flashBytes=(path/'player.bin').stat().st_size,compiledLinkedOnly=True))
    name='low-fusion-controls.json';save(name,dict(images=images,production=production,features=features,cImages=c_images,cDecoderExecuted=False));reports.append(name)
    base=read('noise-prefold-admission.json');sources=list(base['sourceSha256'])+ADDED;assert len(sources)==len(set(sources))
    save('low-fusion-admission.json',dict(baselineRevision='307fe278',baselineAdmissionSha256=sha(ROOT/'reports/noise-prefold-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',backend='explicit AVR ASM',
        compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',physicalBoardTested=False,
        sourceSha256={n:sha(ROOT/n) for n in sources},reportSha256={n:sha(ROOT/'reports'/n) for n in reports},
        admittedExtraCpuCyclesPerFrame=9600,
        limits=['Fresh matched before/after complete decoder, IRQ and SPI runs cover WB5.75/WB7.75.',
                'Five other bare profile images are rebuilt byte-identically; prior evidence is retained for those exact images.',
                'Mixed all-mode API checks cover both APIs; no fresh full all-feature WB3.95/WB9.8/WB12.8 timing claim.',
                'Single-feature ASM images pass three-stream/384-frame screens, not the full corpus.',
                'C decoder is compile/link only; isolated explicit C vector arithmetic is tested.',
                'Small mode dispatch is inline; measured outlined variant is retained as a comparison.',
                'Compact Q7/16-tap QMF and all quantizers remain unchanged; no physical-board or analog claim.']))


def audit(args):
    a=read('low-fusion-admission.json');base=read('noise-prefold-admission.json')
    assert sha(ROOT/'reports/noise-prefold-admission.json')==a['baselineAdmissionSha256']
    assert sorted(n for n,v in base['sourceSha256'].items() if sha(ROOT/n)!=v)==sorted(CHANGED)
    for n,v in a['sourceSha256'].items():assert sha(ROOT/n)==v,n
    for n,v in {**base['reportSha256'],**a['reportSha256']}.items():assert sha(ROOT/'reports'/n)==v,n
    for n,v in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==v,n
    baseline=read('low-fusion-baseline-source.json');assert baseline['sourceTreeVerified'] and baseline['sourceFiles']==len(base['sourceSha256'])
    assert baseline['admissionSha256']==a['baselineAdmissionSha256']
    u=read('low-fusion-unit.json');assert u['cases']==52256 and u['fourPathsExact'] and u['independentBigInt'] and u['pinnedCodebooksExact']
    assert u['allRowsAtEveryVectorSlot'] and u['callerScales']==32 and u['scales']==49 and u['gainEdges']==15 and u['structuredGains']==183
    assert u['randomCasesPerMode']==4096 and u['calleeSavedAndR1Returns']==3*u['cases']
    for key in ['arbitraryNonArgumentRegisterPatterns','argumentRegistersPreserved','readOnlyIndicesAndBounds',
                'exactFlashAddresses','intermediateLoadsAndStoresObserved','outputGuards']:assert u[key],key
    for mode,cases,before_muls,after_muls in [('2',18784,608,604),('8',33472,604,602)]:
        for label in ['before','after','leaf']:
            s=u['asm'][mode][label];assert s['calls']==cases and s['muls']==cases*(before_muls if label=='before' else after_muls)
            assert s['outputReads']==(80*cases if label=='before' else 0) and s['outputWrites']==(160*cases if label=='before' else 80*cases)
    for label,(width,saving) in PROFILES.items():
        before=read('low-fusion-before-'+label+'.json');after=read('low-fusion-after-'+label+'.json')
        assert before['frames']==after['frames']==10627 and len(after['streams'])==18
        assert after['flashBytes']==before['flashBytes']+236 and after['staticSramBytes']==before['staticSramBytes']
        assert after['peakStack']==before['peakStack']-20 and after['freeSram']==before['freeSram']+20
        for x,y in zip(after['streams'],before['streams']):
            assert x['name']==y['name'] and x['frames']==y['frames'] and x['pcmExact'] and y['pcmExact'] and x['reset'] and y['reset']
            assert x['meanCycles']==y['meanCycles']-saving and x['maxCycles']==y['maxCycles']-saving
        assert abs((before['meanCycles']-after['meanCycles'])-saving)<1e-8
        irq=read('low-fusion-irq-'+label+'.json');assert irq['frames']==10627 and irq['includesInterrupts'] and irq['extraCpuCyclesPerFrame']==9600 and irq['underruns']==0
        for row in irq['streams']:
            assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
            assert 990<=row['timerIntervalMinCycles']<=row['timerIntervalMaxCycles']<=1010 and row['refillPublications']==4*row['frames']
        spi=read('low-fusion-spi-'+label+'.json');frames=2200 if label=='wb575' else 1800
        assert spi['passed'] and spi['frames']==frames and spi['input']['streamBytes']==spi['modelStats']['readBytes']==frames*width
        assert spi['includesInterrupts'] and spi['s16Exact'] and spi['pwmExact'] and spi['underruns']==0 and spi['fullHistoryWithoutReset']
        feature=read('low-fusion-feature-'+label+'.json');assert feature['frames']==384 and all(r['pcmExact'] and r['reset'] for r in feature['streams'])
        old_screen=read('low-fusion-screen-before-'+label+'.json');new_screen=read('low-fusion-screen-after-'+label+'.json');outlined=read('low-fusion-outlined-screen-'+label+'.json')
        assert old_screen['frames']==new_screen['frames']==outlined['frames']==384
        assert old_screen['binarySha256']==before['binarySha256'] and new_screen['binarySha256']==after['binarySha256']
        assert new_screen['meanCycles']<outlined['meanCycles']<old_screen['meanCycles']
        assert new_screen['flashBytes']==outlined['flashBytes']-22 and new_screen['peakStack']==outlined['peakStack']-3
    for label,rejects in [('nb',6144),('wb',7168)]:
        api=read('low-fusion-api-'+label+'.json');assert api['frames']==1024 and api['rejectedCalls']==rejects and api['pcmExact'] and api['resetExact']
        f=api['lowFusionArithmetic'];assert f['rejectedCallsAndOtherModesDoNotExecute'] and f['fourCallsPerMatchingWbFrame'] and f['nbApiDoesNotExecute']
        for m,muls in [('2',604),('8',602)]:
            assert f['byMode'][m]['calls']==(820 if label=='wb' else 0) and f['byMode'][m]['muls']==(820*muls if label=='wb' else 0)
    controls=read('low-fusion-controls.json');assert len(controls['images'])==5 and all(r['byteIdentical'] for r in controls['images']) and not controls['cDecoderExecuted']
    assert len(controls['production'])==2 and all(r['oldFoldAndControllerAbsent'] and r['newLeavesPresent'] and r['inlineDispatcherAbsent'] for r in controls['production'])
    assert len(controls['features'])==4 and all(r['unusedKernelAbsent'] for r in controls['features'])
    assert all(r['compiledLinkedOnly'] for r in controls['features'] if r['backend']=='c')
    assert len(controls['cImages'])==2 and all(r['compiledLinkedOnly'] and r['flashBytes']<=32768 for r in controls['cImages'])
    export=read('low-fusion-export.json');assert export['sources']==21 and not export['handwrittenAssembly'] and not export['duplicateSources']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile'] not in PROFILES:continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:assert sha(args.corpus/row['profile']/folder/(stem+suffix),False)==row[key]
        for row in read('low-fusion-screen-corpus.json')['streams']:
            for folder,suffix,size,key in [('streams','.spxraw',PROFILES[row['profile']][0],'input'),('oracle','.pcm',640,'pcm')]:
                data=(args.corpus/row['profile']/folder/(row['stream']+suffix)).read_bytes()
                assert hashlib.sha256(data).hexdigest()==row['source'+key.title()+'Sha256']
                assert hashlib.sha256(data[:128*size]).hexdigest()==row[key+'Sha256']
    print('PASS exact WB5.75/WB7.75 fusion: 52256 cases / 42508 matched raw / 21254 IRQ / 4000 SPI frames')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');p.add_argument('--corpus',type=Path)
    args=p.parse_args()
    if args.record:record()
    audit(args)


if __name__=='__main__':main()
