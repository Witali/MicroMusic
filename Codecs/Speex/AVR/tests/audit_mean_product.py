#!/usr/bin/env python3
"""Audit one-product mean, real decoder operation counts and uninterrupted output."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ADDED=['src/wb_gain_div.h','src/wb_gain_div.S','tests/avr_gain_div.c',
       'tests/build_gain_div.py','tests/verify_gain_div.mjs','src/lowrate_mean.h','src/lowrate_mean.S',
       'tests/avr_low_mean.c','tests/build_low_mean.py','tests/verify_low_mean.mjs',
       'tests/build_mean_admission.py','tests/run_mean_admission.py','tests/audit_mean_product.py']


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,value):
    (ROOT/'reports'/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())


def record(args):
    assert args.gain_build,'Recording needs the matched gain-stage build directory'
    reports=['mean-product-unit.json','gain-div-unit.json']
    for epoch in ['before','after']:
        for label in ['nb215','wb395']:reports.append(f'mean-product-screen-{epoch}-{label}.json')
    save('mean-product-before-nb215.json',read('noise-speed-nb215.json'))
    save('mean-product-before-wb395.json',json.loads((args.gain_build/'gain-after/wb395/verification.json').read_text()))
    reports+=['mean-product-before-nb215.json','mean-product-before-wb395.json']
    for label,filename in [('nb215','avr-verification.json'),('wb395','verification.json'),
                           ('irq','verification.json'),('spi','verification.json'),
                           ('api/nb','verification.json'),('api/wb','verification.json')]:
        name='mean-product-'+label.replace('/','-')+'.json'
        save(name,json.loads((ROOT/'build/mean-final'/label/filename).read_text()));reports.append(name)
    images=[]
    for label in ['nb8','nb11','wb98','wb128']:
        binary='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[ROOT/'build/mean-disabled'/epoch/label/binary for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,binarySha256=sha(paths[1],False),
                           flashBytes=paths[1].stat().st_size,byteIdentical=True))
    c_images=[]
    for label in ['nb11','wb395']:
        binary=ROOT/f'build/mean-c/{label}/player.bin'
        before=args.gain_build/f'gain-c/{label}/player.bin'
        meta=json.loads((binary.parent/'input.json').read_text())
        assert meta['backend']=='c' and meta['binarySha256']==sha(binary,False)
        c_images.append(dict(profile=label,binarySha256=sha(binary,False),flashBytes=binary.stat().st_size,
                             byteIdenticalToGain=before.read_bytes()==binary.read_bytes(),compiledLinkedOnly=True))
    save('mean-product-identities.json',dict(disabledAsm=images,cImages=c_images,cDecoderExecuted=False))
    reports.append('mean-product-identities.json')
    save('mean-product-export.json',json.loads((ROOT/'build/low-export-check.json').read_text()))
    reports.append('mean-product-export.json')
    base=read('noise-cache-admission.json');sources=list(base['sourceSha256'])+ADDED
    assert len(sources)==len(set(sources))
    save('mean-product-admission.json',dict(baselineRevision='4107d9f3',
        baselineNoiseAdmissionSha256=sha(ROOT/'reports/noise-cache-admission.json'),
        target='ATmega328P / 16 MHz / 2 KB SRAM',backend='explicit AVR ASM',physicalBoardTested=False,
        sourceSha256={name:sha(ROOT/name) for name in sources},
        reportSha256={name:sha(ROOT/'reports'/name) for name in reports},
        limits=['Fresh raw runs cover affected NB2.15 and WB3.95; matched before data is retained by image identity.',
                'Other lower-rate-disabled ASM images are rebuilt byte-identically, not rerun.',
                'C decoder is compile/link only; isolated C arithmetic is verified.',
                'IRQ uses ready RAM plus 8% extra load; SPI separately models transport at zero extra load.',
                'Existing compact Q7/16-tap QMF is unchanged; no board/analog claim.']))


def audit(args):
    admission=read('mean-product-admission.json');base=read('noise-cache-admission.json')
    assert sha(ROOT/'reports/noise-cache-admission.json')==admission['baselineNoiseAdmissionSha256']
    changed=sorted(name for name,value in base['sourceSha256'].items() if sha(ROOT/name)!=value)
    assert changed==sorted(['src/lowrate_excitation.h','src/speex_wb1.c','tools/build.py',
                            'tools/build_wb.py','tests/verify_low_api.mjs']),changed
    for name,value in admission['sourceSha256'].items():assert sha(ROOT/name)==value,name
    for name,value in admission['reportSha256'].items():assert sha(ROOT/'reports'/name)==value,name
    for name,value in read('spi-input-admission.json')['sourceSha256'].items():
        assert sha(ROOT.parents[2]/name)==value,name
    unit=read('mean-product-unit.json')
    assert unit['cases']==1212335 and unit['cAndAsmExact'] and unit['hardwareMultipliesPerCall']==4
    assert unit['calleeSavedAndR1Returns']==unit['cases'] and unit['arbitraryRegisterPatterns']
    assert unit['overflowPositive']>0 and unit['overflowNegative']>0
    assert unit['asmFunctionMinCycles']==43 and unit['asmFunctionMaxCycles']==48
    gain=read('gain-div-unit.json');assert gain['cases']==1049060 and gain['cAndAsmExact']
    corpus=read('low-final-corpus.json')['streams']
    for label in ['nb215','wb395']:
        before=read(f'mean-product-before-{label}.json');after=read(f'mean-product-{label}.json')
        screen=read(f'mean-product-screen-before-{label}.json')
        assert before['binarySha256']==screen['binarySha256']
        assert before['frames']==after['frames']==10627 and len(after['streams'])==18
        assert after['maxCycles']<before['maxCycles'] and after['staticSramBytes']==before['staticSramBytes']
        assert after['flashBytes']==before['flashBytes']-(86 if label=='nb215' else 44)
        for a,b in zip(after['streams'],before['streams']):
            key='stream' if label=='nb215' else 'name'
            assert a[key]==b[key] and a['frames']==b['frames']
            assert a['meanCycles']<b['meanCycles']
            assert a['resetVerified'] if label=='nb215' else a['reset'] and a['pcmExact']
        if label=='nb215':assert after['freeSramAtPeak']==before['freeSramAtPeak']+6
        else:assert after['peakStack']==before['peakStack'] and after['meanCycles']<before['meanCycles']
        if args.corpus:
            for row in corpus:
                if row['profile']!=label:continue
                stem=Path(row['stream']).stem
                for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:
                    assert sha(args.corpus/label/folder/(stem+suffix),False)==row[key]
    irq=read('mean-product-irq.json')
    assert irq['frames']==10627 and irq['includesInterrupts'] and irq['extraCpuCyclesPerFrame']==25600
    assert irq['underruns']==0 and irq['freeSramAtPeak']>0
    for row in irq['streams']:
        assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
        assert row['timerIntervalMinCycles']>=990 and row['timerIntervalMaxCycles']<=1010
    spi=read('mean-product-spi.json')
    assert spi['passed'] and spi['frames']==3600 and spi['input']['streamBytes']==36000
    assert spi['includesInterrupts'] and spi['s16Exact'] and spi['pwmExact'] and spi['underruns']==0
    assert spi['fullHistoryWithoutReset'] and spi['modelStats']['readBytes']==36000
    assert spi['pwmSha256']==read('noise-cache-spi-wb395.json')['pwmSha256']
    for label,rejects in [('nb',6144),('wb',7168)]:
        api=read('mean-product-api-'+label+'.json');math=api['meanArithmetic']
        assert api['frames']==1024 and api['rejectedCalls']==rejects and api['pcmExact'] and api['resetExact']
        assert math['calls']==32960 and math['hardwareMultiplies']==131840
        assert math['hardwareMultipliesPerNb1Frame']==640 and math['exactDuringDecoder'] and math['rejectedCallsDoNotExecute']
    identity=read('mean-product-identities.json')
    assert len(identity['disabledAsm'])==4 and all(row['byteIdentical'] for row in identity['disabledAsm'])
    assert identity['cDecoderExecuted'] is False and len(identity['cImages'])==2
    assert all(row['compiledLinkedOnly'] and row['flashBytes']<=32768 for row in identity['cImages'])
    export=read('mean-product-export.json');assert not export['handwrittenAssembly'] and not export['duplicateSources']
    print('PASS one-product mean: 21254 raw / 10627 loaded IRQ / 3600 SPI frames; actual four-MUL counts and exact C fallback')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record',action='store_true')
    p.add_argument('--gain-build',type=Path,help='Matched gain-stage AVR/build directory')
    p.add_argument('--corpus',type=Path,help='Optional lower-rate corpus for input/oracle hashes')
    args=p.parse_args()
    if args.record:record(args)
    audit(args)


if __name__=='__main__':main()
