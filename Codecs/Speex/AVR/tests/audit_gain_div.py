#!/usr/bin/env python3
"""Audit exact bounded division, matched five-mode cycles and active-output evidence."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROFILES={'wb395':(10,10627,25600),'wb575':(15,10627,9600),
          'wb775':(20,10627,9600),'wb98':(25,10563,25600),'wb128':(32,10563,25600)}
NEW_SOURCES=['src/wb_gain_div.h','src/wb_gain_div.S','tests/avr_gain_div.c',
             'tests/build_gain_div.py','tests/verify_gain_div.mjs','tests/build_gain_admission.py',
             'tests/run_gain_admission.py','tests/audit_gain_div.py']


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,value):
    (ROOT/'reports'/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())


def corpus_path(args,label):
    if label in ['wb395','wb575','wb775']:return args.low_corpus/label
    return args.legacy_corpus/('wb-corpus' if label=='wb98' else 'higher-corpus/wb128')


def record(args):
    assert args.low_corpus and args.legacy_corpus,'Recording requires both corpora'
    reports=['gain-div-unit.json','gain-div-screen.json']
    for label in PROFILES:
        for phase in ['before','after','irq']:
            name=f'gain-div-{phase}-{label}.json'
            save(name,json.loads((ROOT/f'build/gain-{phase}/{label}/verification.json').read_text()))
            reports.append(name)
    for phase,labels in [('spi',['wb395','wb128']),('api',['nb','wb'])]:
        for label in labels:
            name=f'gain-div-{phase}-{label}.json'
            save(name,json.loads((ROOT/f'build/gain-{phase}/{label}/verification.json').read_text()))
            reports.append(name)
    save('gain-div-export.json',json.loads((ROOT/'build/low-export-check.json').read_text()))
    reports.append('gain-div-export.json')
    identities=[]
    old_c={row['profile']:row for row in read('noise-cache-identities.json')['cImages']}
    for label in ['nb11','wb395']:
        binary=ROOT/f'build/gain-c/{label}/player.bin'
        actual=sha(binary,False);meta=json.loads((binary.parent/'input.json').read_text())
        assert actual==meta['binarySha256'] and meta['backend']=='c'
        before=old_c[label]
        if label=='wb395':
            old=ROOT/f'build/gain-c-before/{label}/player.bin'
            assert sha(old,False)==before['binarySha256']
        identities.append(dict(profile=label,binarySha256=actual,flashBytes=binary.stat().st_size,
            beforeSha256=before['binarySha256'],beforeFlashBytes=before['flashBytes'],
            byteIdentical=actual==before['binarySha256'],compiledLinkedOnly=True))
    save('gain-div-identities.json',dict(cImages=identities,cDecoderExecuted=False))
    reports.append('gain-div-identities.json')
    rows=[]
    for label,(width,_,_) in PROFILES.items():
        directory=corpus_path(args,label)
        for path in sorted((directory/'streams').glob('*.spxraw')):
            pcm=directory/'oracle'/(path.stem+'.pcm')
            assert path.stat().st_size%width==0
            frames=path.stat().st_size//width
            assert pcm.stat().st_size==frames*640
            rows.append(dict(profile=label,stream=path.name,frames=frames,
                             inputSha256=sha(path,False),pcmSha256=sha(pcm,False)))
    save('gain-div-corpus.json',dict(streams=rows,frames=sum(row['frames'] for row in rows)))
    reports.append('gain-div-corpus.json')
    base=read('noise-cache-admission.json')
    sources=list(base['sourceSha256'])+NEW_SOURCES
    assert len(sources)==len(set(sources))
    save('gain-div-admission.json',dict(baselineRevision='3a0462fb',
        baselineAdmissionSha256=sha(ROOT/'reports/noise-cache-admission.json'),
        target='ATmega328P / 16 MHz / 2 KB SRAM',backend='explicit AVR ASM',physicalBoardTested=False,
        sourceSha256={name:sha(ROOT/name) for name in sources},
        reportSha256={name:sha(ROOT/'reports'/name) for name in reports},
        limits=['C decoder compiled/linked only; isolated scalar C fallback is checked.',
                'Ready-RAM IRQ gates retain established per-mode extra loads, not equal load for all modes.',
                'SPI has active interrupts and actual input latency but no additional foreground load.',
                'Compact Q7/16-tap QMF and all arithmetic rounding are unchanged.']))


def audit(args):
    admission=read('gain-div-admission.json');base=read('noise-cache-admission.json')
    assert sha(ROOT/'reports/noise-cache-admission.json')==admission['baselineAdmissionSha256']
    changed=sorted(name for name,value in base['sourceSha256'].items() if sha(ROOT/name)!=value)
    assert changed==['src/speex_wb1.c','tools/build_wb.py'],changed
    for name,value in admission['sourceSha256'].items():assert sha(ROOT/name)==value,name
    for name,value in admission['reportSha256'].items():assert sha(ROOT/'reports'/name)==value,name
    for name,value in read('spi-input-admission.json')['sourceSha256'].items():
        assert sha(ROOT.parents[2]/name)==value,name
    unit=read('gain-div-unit.json')
    assert unit['cases']==1049060 and unit['tableDivisorPairs']==32*32767 and unit['cAndAsmExact']
    assert unit['calleeSavedAndR1Returns']==unit['cases'] and unit['arbitraryRegisterPatterns']
    assert unit['quotientLowSteps']==16 and unit['remainderBits']==16
    assert unit['energyMax']==904448 and unit['roundedNumeratorMax']==920831
    corpus=read('gain-div-corpus.json');assert corpus['frames']==53007
    raw_frames=irq_frames=0
    for label,(width,frames,load) in PROFILES.items():
        before=read(f'gain-div-before-{label}.json');after=read(f'gain-div-after-{label}.json')
        assert before['frames']==after['frames']==frames
        assert after['flashBytes']==before['flashBytes']+8
        assert after['staticSramBytes']==before['staticSramBytes']
        assert after['peakStack']==before['peakStack']
        assert after['meanCycles']<before['meanCycles'] and after['maxCycles']<before['maxCycles']
        expected={row['stream']:row for row in corpus['streams'] if row['profile']==label}
        assert len(after['streams'])==len(expected)
        for a,b in zip(after['streams'],before['streams']):
            assert a['name']==b['name'] and a['frames']==b['frames']==expected[a['name']]['frames']
            assert a['pcmExact'] and a['reset'] and b['pcmExact'] and b['reset']
        irq=read(f'gain-div-irq-{label}.json')
        assert irq['packetBytes']==width and irq['frames']==frames and irq['includesInterrupts']
        assert irq['extraCpuCyclesPerFrame']==load and irq['underruns']==0 and irq['freeSramAtPeak']>0
        for row in irq['streams']:
            assert row['s16AndPwmExact'] and row['fullHistoryWithoutChunkReset'] and row['underruns']==0
            assert row['timerIntervalMinCycles']>=990 and row['timerIntervalMaxCycles']<=1010
            for key in ['inputSha256','pcmSha256']:assert row[key]==expected[row['stream']][key]
        if args.low_corpus and args.legacy_corpus:
            directory=corpus_path(args,label)
            for row in expected.values():
                assert sha(directory/'streams'/row['stream'],False)==row['inputSha256']
                assert sha(directory/'oracle'/(Path(row['stream']).stem+'.pcm'),False)==row['pcmSha256']
        raw_frames+=frames*2;irq_frames+=frames
    for label,frames,nbytes in [('wb395',3600,36000),('wb128',2200,70400)]:
        spi=read(f'gain-div-spi-{label}.json')
        assert spi['passed'] and spi['frames']==frames and spi['input']['streamBytes']==nbytes
        assert spi['includesInterrupts'] and spi['s16Exact'] and spi['pwmExact'] and spi['underruns']==0
        assert spi['fullHistoryWithoutReset'] and spi['freeSramAtPeak']>0
        assert spi['modelStats']['readBytes']==nbytes and spi['modelStats']['transferCalls']==nbytes+5
        old=read('noise-cache-spi-'+label+'.json');assert spi['pwmSha256']==old['pwmSha256']
    for label,rejected in [('nb',6144),('wb',7168)]:
        api=read('gain-div-api-'+label+'.json')
        assert api['frames']==1024 and api['rejectedCalls']==rejected and api['pcmExact'] and api['resetExact']
    identity=read('gain-div-identities.json');assert identity['cDecoderExecuted'] is False
    assert len(identity['cImages'])==2 and all(row['compiledLinkedOnly'] and row['flashBytes']<=32768 for row in identity['cImages'])
    export=read('gain-div-export.json');assert not export['duplicateSources'] and not export['handwrittenAssembly']
    assert export['widebandBitrates']==[3950,5750,7750,9800,12800]
    print(f'PASS bounded division: {raw_frames} matched raw / {irq_frames} IRQ / 5800 SPI frames; exact PCM and C fallback')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--record',action='store_true',help='Retain completed local run evidence, then audit it')
    p.add_argument('--low-corpus',type=Path)
    p.add_argument('--legacy-corpus',type=Path)
    args=p.parse_args()
    if args.record:record(args)
    audit(args)


if __name__=='__main__':main()
