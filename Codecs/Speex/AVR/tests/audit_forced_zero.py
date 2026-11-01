#!/usr/bin/env python3
"""Bind zero-coefficient prediction elision to exact state, timing and output."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROFILES={'nb395':False,'wb575':True}
CHANGED=['src/lowrate_excitation.h','src/zero_innovation.h','src/innovation.S',
         'tests/verify_avr.mjs','tests/verify_wb.mjs','tests/verify_low_api.mjs']
ADDED=['tests/avr_zero20.c','tests/build_zero20.py','tests/verify_zero20.mjs',
       'tests/build_forced_zero_admission.py','tests/run_forced_zero_admission.py','tests/audit_forced_zero.py']


def sha(path,text=True):
    data=path.read_bytes()
    return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,data):(ROOT/'reports'/name).write_bytes((json.dumps(data,indent=2)+'\n').encode())
def report_name(wb):return 'verification.json' if wb else 'avr-verification.json'


def paired_timing():
    result={};out=ROOT/'build/forced-zero-final'
    for label,wb in PROFILES.items():
        before,after=[json.loads((out/epoch/label/'forced-zero-timing.json').read_text()) for epoch in ['before','after']]
        assert before['frames']==after['frames']==10627 and before['packetBytes']==after['packetBytes']
        for epoch,t in [('before',before),('after',after)]:
            assert t['binarySha256']==json.loads((out/epoch/label/report_name(wb)).read_text())['binarySha256']
        groups={k:dict(frames=0,beforeCycles=0,afterCycles=0,deltaMin=None,deltaMax=None) for k in ['zero','nonzero']}
        rows=[];speech=dict(frames=0,zeroFrames=0,beforeCycles=0,afterCycles=0)
        for old,new in zip(before['streams'],after['streams']):
            assert old['stream']==new['stream'] and old['inputSha256']==new['inputSha256'] and old['pcmSha256']==new['pcmSha256']
            assert old['coefficientZero']==new['coefficientZero'] and len(old['cycles'])==len(new['cycles'])==len(old['coefficientZero'])
            zero_count=sum(old['coefficientZero']);a=sum(old['cycles']);b=sum(new['cycles'])
            row=dict(stream=old['stream'],frames=len(old['cycles']),zeroFrames=zero_count,beforeCycles=a,afterCycles=b)
            for z,x,y in zip(old['coefficientZero'],old['cycles'],new['cycles']):
                g=groups['zero' if z else 'nonzero'];delta=y-x;g['frames']+=1;g['beforeCycles']+=x;g['afterCycles']+=y
                g['deltaMin']=delta if g['deltaMin'] is None else min(g['deltaMin'],delta)
                g['deltaMax']=delta if g['deltaMax'] is None else max(g['deltaMax'],delta)
            if old['stream'].startswith(('en_','ru_')):
                speech['frames']+=row['frames'];speech['zeroFrames']+=zero_count;speech['beforeCycles']+=a;speech['afterCycles']+=b
            rows.append(row)
        for epoch in ['before','after']:speech[epoch+'MeanCycles']=speech[epoch+'Cycles']/speech['frames']
        result[label]=dict(beforeBinarySha256=before['binarySha256'],afterBinarySha256=after['binarySha256'],frames=before['frames'],
            groups=groups,speech=speech,streams=rows)
    return dict(scope='Matched per-frame command intervals; mailbox included, startup/reset/ISR excluded',profiles=result)


def record():
    reports=[];out=ROOT/'build/forced-zero-final'

    def retain(label,path):
        name='forced-zero-'+label+'.json';save(name,json.loads(path.read_text()));reports.append(name)

    for label,path in [('unit','zero20-unit/verification.json'),('unit-image','zero20-unit/input.json'),
                       ('corpus','forced-zero-screen-data/manifest.json'),('export','low-export-check.json')]:retain(label,ROOT/'build'/path)
    retain('baseline-source',out/'baseline-source.json')
    for label,wb in PROFILES.items():
        for epoch in ['before','after']:retain(epoch+'-'+label,out/epoch/label/report_name(wb))
        retain('spi-'+label,out/'spi'/label/'verification.json')
        retain('feature-'+label,out/'features/asm'/label/report_name(wb))
        retain('screen-before-'+label,ROOT/'build/forced-zero-screen/before'/label/report_name(wb))
        retain('postquant-screen-'+label,ROOT/'build/forced-zero-postquant-screen'/label/report_name(wb))
        retain('screen-after-'+label,ROOT/'build/forced-zero-raw-screen'/label/report_name(wb))
    retain('irq-wb575',out/'irq/wb575/verification.json')
    for label in ['nb','wb']:retain('api-'+label,out/'api'/label/'verification.json')
    name='forced-zero-timing.json';save(name,paired_timing());reports.append(name)
    images=[]
    for label in ['nb8','nb11','wb98','wb128']:
        filename='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[out/'identities'/epoch/label/filename for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,binarySha256=sha(paths[1],False),flashBytes=paths[1].stat().st_size,byteIdentical=True))
    features=[];c_images=[]
    for label,wb in PROFILES.items():
        for backend in ['asm','c']:
            path=out/'features'/backend/label;meta=json.loads((path/'backend.json').read_text());symbols=(path/'symbols.txt').read_text()
            filename='wb.bin' if wb else 'speex-test.bin';assert sha(path/filename,False)==meta['binarySha256']
            assert meta['lowRates']==2 and ('speex_avr_zero_innovation_n' in symbols)==(backend=='asm')
            assert 'speex_nb8_zero_frame' in symbols
            features.append(dict(profile=label,backend=backend,binarySha256=meta['binarySha256'],flashBytes=(path/filename).stat().st_size,
                lowRates=2,selectedBackendVerified=True,compiledLinkedOnly=backend=='c'))
        path=out/'c'/label;meta=json.loads((path/'input.json').read_text());assert meta['backend']=='c' and sha(path/'player.bin',False)==meta['binarySha256']
        c_images.append(dict(profile=label,binarySha256=meta['binarySha256'],flashBytes=(path/'player.bin').stat().st_size,compiledLinkedOnly=True))
    name='forced-zero-controls.json';save(name,dict(images=images,features=features,cImages=c_images,cDecoderExecuted=False));reports.append(name)
    base=read('low-fusion-admission.json');sources=list(base['sourceSha256'])+ADDED;assert len(sources)==len(set(sources))
    save('forced-zero-admission.json',dict(baselineRevision='056d3a73',baselineAdmissionSha256=sha(ROOT/'reports/low-fusion-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',backend='explicit AVR ASM',
        compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',physicalBoardTested=False,
        sourceSha256={n:sha(ROOT/n) for n in sources},reportSha256={n:sha(ROOT/'reports'/n) for n in reports},admittedExtraCpuCyclesPerFrame=9600,
        limits=['Fresh matched complete decoders cover NB3.95 and WB5.75; loaded ready-RAM IRQ covers WB5.75.',
                'SPI covers NB3.95 coverage4096 and WB5.75 long2200 with continuous history.',
                'Four minimum images without NB8 are byte-identical; no fresh full other-profile timing claim.',
                'Single-feature ASM images pass 384-frame screens; C controls/export compile/link only.',
                'Isolated C arithmetic is executed; the C decoder is not executed or timed.',
                'WB peak stack is unchanged; standalone NB3.95 peak stack increases six bytes.',
                'QMF/rounding/packet formats stay unchanged; no physical-board or analog claim.']))


def audit(args):
    a=read('forced-zero-admission.json');base=read('low-fusion-admission.json')
    assert sha(ROOT/'reports/low-fusion-admission.json')==a['baselineAdmissionSha256']
    assert sorted(n for n,v in base['sourceSha256'].items() if sha(ROOT/n)!=v)==sorted(CHANGED)
    for n,v in a['sourceSha256'].items():assert sha(ROOT/n)==v,n
    for n,v in {**base['reportSha256'],**a['reportSha256']}.items():assert sha(ROOT/'reports'/n)==v,n
    for n,v in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==v,n
    b=read('forced-zero-baseline-source.json');assert b['sourceTreeVerified'] and b['sourceFiles']==len(base['sourceSha256']) and b['admissionSha256']==a['baselineAdmissionSha256']
    u=read('forced-zero-unit.json');im=read('forced-zero-unit-image.json')
    assert im['arithmeticFirmwareUnchanged'] and im['beforeBinarySha256']==im['binarySha256']==u['binarySha256']
    assert u['cases']==37024 and u['originalQ14AndCollapsedFormulaExact'] and u['cAndAsmExact'] and u['counts0Through20']
    assert u['all32Rows'] and u['callerScales']==32 and u['uniqueScales']==49 and u['randomCases']==4096 and u['calleeSavedAndR1Returns']==42354
    for key in ['zeroNullPointersAndNoDataAccess','outputGuardsAndTail','exactFlashAddresses','outputNotRead','arbitraryNonArgumentRegisterPatterns','countArgumentPreserved']:assert u[key],key
    assert u['fixedTen']['minCycles']==u['fixedTen']['maxCycles']==501
    for row in u['variable']:
        assert row['muls']==4*row['count']*row['calls'] and row['minCycles']==row['maxCycles']==(6 if not row['count'] else 45+46*row['count'])
    timing=read('forced-zero-timing.json')['profiles'];counts={r['profile']:r for r in read('forced-zero-corpus.json')['counts']}
    assert all((min(63,(2185*(k<<6)+16384)>>15)==0)==(k==0) for k in range(16))
    for label,wb in PROFILES.items():
        old=read('forced-zero-before-'+label+'.json');new=read('forced-zero-after-'+label+'.json');t=timing[label]
        assert old['frames']==new['frames']==10627 and len(old['streams'])==len(new['streams'])==18
        assert new['flashBytes']==old['flashBytes']+(144 if wb else 138) and new['staticSramBytes']==old['staticSramBytes']
        for x,y in zip(old['streams'],new['streams']):
            assert x.get('name',x.get('stream'))==y.get('name',y.get('stream')) and x['frames']==y['frames']
            assert x.get('reset',x.get('resetVerified')) and y.get('reset',y.get('resetVerified'))
        if wb:assert new['peakStack']==old['peakStack'] and new['freeSram']==old['freeSram']
        else:assert new['minStackPointer']==old['minStackPointer']-6 and new['freeSramAtPeak']==old['freeSramAtPeak']-6
        assert t['beforeBinarySha256']==old['binarySha256'] and t['afterBinarySha256']==new['binarySha256']
        assert sum(g['frames'] for g in t['groups'].values())==10627
        assert t['groups']['zero']['frames']==counts[label]['zeroCoefficientFrames']==(2223 if wb else 2243)
        assert t['groups']['nonzero']['deltaMin']==t['groups']['nonzero']['deltaMax']==-4
        assert (t['groups']['zero']['deltaMin'],t['groups']['zero']['deltaMax'])==((-27464,-16728) if wb else (-27448,-16720))
        assert t['speech']['frames']==6467 and t['speech']['zeroFrames']==counts[label]['speechZeroCoefficientFrames']==(1903 if wb else 1923)
        assert t['speech']['afterMeanCycles']<t['speech']['beforeMeanCycles'] and new['maxCycles']==old['maxCycles']-4
        s=read('forced-zero-spi-'+label+'.json');frames=2200 if wb else 4096;width=15 if wb else 10
        assert s['passed'] and s['frames']==frames and s['s16Exact'] and s['pwmExact'] and s['underruns']==0 and s['includesInterrupts'] and s['fullHistoryWithoutReset']
        assert s['input']['streamBytes']==s['modelStats']['readBytes']==frames*width
        f=read('forced-zero-feature-'+label+'.json');assert f['frames']==384 and all(r.get('reset',r.get('resetVerified')) for r in f['streams'])
        post=read('forced-zero-postquant-screen-'+label+'.json');selected=read('forced-zero-screen-after-'+label+'.json');before_screen=read('forced-zero-screen-before-'+label+'.json')
        assert selected['frames']==post['frames']==before_screen['frames']==384 and selected['binarySha256']==new['binarySha256'] and before_screen['binarySha256']==old['binarySha256']
        assert selected['flashBytes']==post['flashBytes']-12
    irq=read('forced-zero-irq-wb575.json');assert irq['frames']==10627 and irq['extraCpuCyclesPerFrame']==9600 and irq['underruns']==0 and irq['includesInterrupts']
    for r in irq['streams']:assert r['s16AndPwmExact'] and r['fullHistoryWithoutChunkReset'] and r['underruns']==0 and 990<=r['timerIntervalMinCycles']<=r['timerIntervalMaxCycles']<=1010
    for label,frames,rejects in [('nb',42,6144),('wb',44,7168)]:
        p=read('forced-zero-api-'+label+'.json');assert p['frames']==1024 and p['rejectedCalls']==rejects and p['pcmExact'] and p['resetExact']
        z=p['forcedZeroArithmetic'];assert z['frames']==frames and z['twentyWordCalls']==8*frames and z['hardwareMultiplies']==652*frames
        assert z['minMultipliesPerFrame']==z['maxMultipliesPerFrame']==652 and z['noAdaptiveKernel'] and z['noExcitationHistoryOrOutputReads'] and z['invalidAndNonzeroCoefficientCallsDoNotExecute']
    c=read('forced-zero-controls.json');assert len(c['images'])==4 and all(i['byteIdentical'] for i in c['images']) and not c['cDecoderExecuted']
    assert len(c['features'])==4 and all(i['selectedBackendVerified'] and i['lowRates']==2 for i in c['features'])
    assert all(i['compiledLinkedOnly'] for i in c['features'] if i['backend']=='c') and len(c['cImages'])==2 and all(i['compiledLinkedOnly'] and i['flashBytes']<=32768 for i in c['cImages'])
    e=read('forced-zero-export.json');assert e['sources']==21 and not e['handwrittenAssembly'] and not e['duplicateSources']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile'] not in PROFILES:continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:assert sha(args.corpus/row['profile']/folder/(stem+suffix),False)==row[key]
    print('PASS forced coefficient0: 37024 arithmetic cases / 42508 matched raw / 10627 IRQ / 6296 SPI frames; exact PCM/PWM')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');p.add_argument('--corpus',type=Path)
    args=p.parse_args()
    if args.record:record()
    audit(args)


if __name__=='__main__':main()
