#!/usr/bin/env python3
"""Audit exact power-of-two noise scales and their active-output admission."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ADDED=['tests/avr_noise_values.c','tests/build_noise_values.py','tests/verify_noise_values.mjs',
       'tests/build_noise_shift_admission.py','tests/run_noise_shift_admission.py','tests/audit_noise_shifts.py']


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,value):
    (ROOT/'reports'/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())


def record():
    reports=[]
    save('noise-shift-unit.json',json.loads((ROOT/'build/noise-values-unit/verification.json').read_text()))
    reports.append('noise-shift-unit.json')
    for label in ['nb215','wb395']:
        name=f'noise-shift-before-{label}.json';save(name,read(f'mean-product-{label}.json'));reports.append(name)
    for label,filename in [('nb215','avr-verification.json'),('wb395','verification.json'),
                           ('irq','verification.json'),('spi','verification.json'),
                           ('api/nb','verification.json'),('api/wb','verification.json')]:
        name='noise-shift-'+label.replace('/','-')+'.json'
        save(name,json.loads((ROOT/'build/noise-shift-final'/label/filename).read_text()));reports.append(name)
    images=[]
    for label in ['nb8','nb11','wb98','wb128']:
        binary='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[ROOT/'build/noise-shift-disabled'/epoch/label/binary for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,binarySha256=sha(paths[1],False),
                           flashBytes=paths[1].stat().st_size,byteIdentical=True))
    before_c={row['profile']:row for row in read('mean-product-identities.json')['cImages']}
    c_images=[]
    for label in ['nb11','wb395']:
        binary=ROOT/f'build/noise-shift-c/{label}/player.bin'
        meta=json.loads((binary.parent/'input.json').read_text());before=before_c[label]
        assert meta['backend']=='c' and meta['binarySha256']==sha(binary,False)
        c_images.append(dict(profile=label,binarySha256=sha(binary,False),flashBytes=binary.stat().st_size,
                             beforeSha256=before['binarySha256'],beforeFlashBytes=before['flashBytes'],compiledLinkedOnly=True))
    save('noise-shift-identities.json',dict(disabledAsm=images,cImages=c_images,cDecoderExecuted=False))
    reports.append('noise-shift-identities.json')
    save('noise-shift-export.json',json.loads((ROOT/'build/low-export-check.json').read_text()))
    reports.append('noise-shift-export.json')
    base=read('mean-product-admission.json');sources=list(base['sourceSha256'])+ADDED
    assert len(sources)==len(set(sources))
    save('noise-shift-admission.json',dict(baselineRevision='c0619042',
        baselineAdmissionSha256=sha(ROOT/'reports/mean-product-admission.json'),
        target='ATmega328P / 16 MHz / 2 KB SRAM',backend='explicit AVR ASM',physicalBoardTested=False,
        sourceSha256={name:sha(ROOT/name) for name in sources},
        reportSha256={name:sha(ROOT/'reports'/name) for name in reports},
        limits=['Fresh raw runs cover affected NB2.15 and WB3.95; unchanged minimum modes retain prior evidence.',
                'C decoder is compile/link only; old/new scalar C and ASM table paths are verified.',
                'IRQ uses ready RAM plus 8% extra load; SPI separately models transport at zero extra load.',
                'The caller scale is positive <=115088100; the table primitive is proven/tested over 0..121000000.',
                'Existing compact Q7/16-tap QMF is unchanged; no board/analog claim.']))


def audit(args):
    admission=read('noise-shift-admission.json');base=read('mean-product-admission.json')
    assert sha(ROOT/'reports/mean-product-admission.json')==admission['baselineAdmissionSha256']
    changed=sorted(name for name,value in base['sourceSha256'].items() if sha(ROOT/name)!=value)
    assert changed==sorted(['src/avr_shift.h','src/lowrate_noise.c','src/lowrate_noise.h','tests/verify_low_api.mjs']),changed
    for name,value in admission['sourceSha256'].items():assert sha(ROOT/name)==value,name
    for name,value in admission['reportSha256'].items():assert sha(ROOT/'reports'/name)==value,name
    for name,value in read('spi-input-admission.json')['sourceSha256'].items():
        assert sha(ROOT.parents[2]/name)==value,name
    unit=read('noise-shift-unit.json')
    assert unit['cases']==228595 and unit['fourPathsExact'] and unit['arbitraryRegisterPatterns']
    assert unit['calleeSavedAndR1Returns']==unit['cases']*2 and unit['outputGuards'] and unit['readonlyScale']
    assert unit['scaleMin']==0 and unit['scaleMax']==121000000 and unit['callerTableScales']==32
    assert unit['callerScaleMax']==115088100 and unit['residuePeriod']==16384 and unit['fullResidueSweeps']==7
    assert unit['baselineNoiseSourceSha256']==base['sourceSha256']['src/lowrate_noise.c']
    for epoch,muls,cycles in [('before',32,729),('after',0,98)]:
        s=unit['asm'][epoch];assert s['calls']==unit['cases'] and s['muls']==muls*unit['cases']
        assert s['minCycles']==s['maxCycles']==cycles
    corpus=read('low-final-corpus.json')['streams']
    for label in ['nb215','wb395']:
        before=read(f'noise-shift-before-{label}.json');after=read(f'noise-shift-{label}.json')
        assert before==read(f'mean-product-{label}.json')
        assert before['frames']==after['frames']==10627 and len(after['streams'])==18
        assert after['maxCycles']<before['maxCycles'] and after['staticSramBytes']==before['staticSramBytes']
        assert after['flashBytes']<before['flashBytes']
        for a,b in zip(after['streams'],before['streams']):
            key='stream' if label=='nb215' else 'name'
            assert a[key]==b[key] and a['frames']==b['frames'] and a['meanCycles']<b['meanCycles']
            assert a['resetVerified'] if label=='nb215' else a['reset'] and a['pcmExact']
        if label=='nb215':assert after['freeSramAtPeak']>=before['freeSramAtPeak']
        else:assert after['peakStack']<=before['peakStack'] and after['meanCycles']<before['meanCycles']
        if args.corpus:
            for row in corpus:
                if row['profile']!=label:continue
                stem=Path(row['stream']).stem
                for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:
                    assert sha(args.corpus/label/folder/(stem+suffix),False)==row[key]
    irq=read('noise-shift-irq.json')
    assert irq['frames']==10627 and irq['includesInterrupts'] and irq['extraCpuCyclesPerFrame']==25600
    assert irq['underruns']==0 and irq['freeSramAtPeak']>0
    for row in irq['streams']:
        assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
        assert row['timerIntervalMinCycles']>=990 and row['timerIntervalMaxCycles']<=1010
    spi=read('noise-shift-spi.json')
    assert spi['passed'] and spi['frames']==3600 and spi['input']['streamBytes']==36000
    assert spi['includesInterrupts'] and spi['s16Exact'] and spi['pwmExact'] and spi['underruns']==0
    assert spi['fullHistoryWithoutReset'] and spi['modelStats']['readBytes']==36000
    assert spi['pwmSha256']==read('mean-product-spi.json')['pwmSha256']
    for label,rejects in [('nb',6144),('wb',7168)]:
        api=read('noise-shift-api-'+label+'.json');table=api['noiseTableArithmetic']
        assert api['frames']==1024 and api['rejectedCalls']==rejects and api['pcmExact'] and api['resetExact']
        assert table==dict(calls=206,hardwareMultiplies=0,callsPerNb1Frame=1,valuesPerCall=5,rejectedCallsDoNotExecute=True)
        assert api['meanArithmetic']['calls']==32960 and api['meanArithmetic']['hardwareMultiplies']==131840
    identity=read('noise-shift-identities.json')
    assert len(identity['disabledAsm'])==4 and all(row['byteIdentical'] for row in identity['disabledAsm'])
    assert identity['cDecoderExecuted'] is False and len(identity['cImages'])==2
    assert all(row['compiledLinkedOnly'] and row['flashBytes']<=32768 for row in identity['cImages'])
    export=read('noise-shift-export.json');assert not export['handwrittenAssembly'] and not export['duplicateSources']
    print('PASS noise shifts: 228595 four-path scales / 21254 raw / 10627 loaded IRQ / 3600 SPI frames; exact PCM')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record',action='store_true')
    p.add_argument('--corpus',type=Path,help='Optional lower-rate corpus for input/oracle hashes')
    args=p.parse_args()
    if args.record:record()
    audit(args)


if __name__=='__main__':main()
