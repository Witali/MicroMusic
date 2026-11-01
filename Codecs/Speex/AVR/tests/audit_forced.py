#!/usr/bin/env python3
"""Bind exact one-tap arithmetic to source, complete PCM and continuous PWM."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHANGED=['src/innovation.S','src/lowrate_excitation.h','tests/verify_low_api.mjs']
ADDED=['src/forced_pitch.h','tests/avr_forced.c','tests/build_forced.py','tests/verify_forced.mjs',
       'tests/build_forced_admission.py','tests/run_forced_admission.py','tests/audit_forced.py']
PROFILES={'nb395':False,'wb575':True}


def sha(path,text=True):
    data=path.read_bytes();return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,data):(ROOT/'reports'/name).write_bytes((json.dumps(data,indent=2)+'\n').encode())
def filename(wb):return 'verification.json' if wb else 'avr-verification.json'


def paired():
    out=ROOT/'build/forced-final';profiles={}
    for label,wb in PROFILES.items():
        before,after=[json.loads((out/epoch/label/'forced-zero-timing.json').read_text()) for epoch in ['before','after']]
        assert before['frames']==after['frames']==10627 and before['packetBytes']==after['packetBytes']
        groups={k:dict(frames=0,beforeCycles=0,afterCycles=0,deltaMin=None,deltaMax=None) for k in ['zero','nonzero']}
        speech=dict(frames=0,beforeCycles=0,afterCycles=0);rows=[]
        for a,b in zip(before['streams'],after['streams']):
            assert a['stream']==b['stream'] and a['inputSha256']==b['inputSha256'] and a['pcmSha256']==b['pcmSha256']
            assert a['coefficientZero']==b['coefficientZero'] and len(a['cycles'])==len(b['cycles'])==len(a['coefficientZero'])
            row=dict(stream=a['stream'],frames=len(a['cycles']),beforeCycles=sum(a['cycles']),afterCycles=sum(b['cycles']))
            for z,x,y in zip(a['coefficientZero'],a['cycles'],b['cycles']):
                g=groups['zero' if z else 'nonzero'];d=y-x;g['frames']+=1;g['beforeCycles']+=x;g['afterCycles']+=y
                g['deltaMin']=d if g['deltaMin'] is None else min(g['deltaMin'],d)
                g['deltaMax']=d if g['deltaMax'] is None else max(g['deltaMax'],d)
                if z:g.setdefault('deltaCounts',{})[str(d)]=g.setdefault('deltaCounts',{}).get(str(d),0)+1
            if a['stream'].startswith(('en_','ru_')):
                speech['frames']+=row['frames'];speech['beforeCycles']+=row['beforeCycles'];speech['afterCycles']+=row['afterCycles']
            rows.append(row)
        for epoch in ['before','after']:speech[epoch+'MeanCycles']=speech[epoch+'Cycles']/speech['frames']
        profiles[label]=dict(beforeBinarySha256=before['binarySha256'],afterBinarySha256=after['binarySha256'],frames=10627,
            groups=groups,speech=speech,streams=rows)
    return dict(scope='Exact paired per-frame command sums; no IRQ, startup or reset',profiles=profiles)


def record():
    out=ROOT/'build/forced-final';reports=[]
    def retain(name,path):
        name='forced-one-'+name+'.json';save(name,json.loads(path.read_text()));reports.append(name)
    retain('unit',ROOT/'build/forced-unit/verification.json');retain('unit-image',ROOT/'build/forced-unit/input.json')
    retain('baseline-source',out/'baseline-source.json');retain('export',ROOT/'build/low-export-check.json');retain('layout',out/'layout.json')
    for label,wb in PROFILES.items():
        for epoch in ['before','after']:retain(epoch+'-'+label,out/epoch/label/filename(wb))
        retain('spi-'+label,out/'spi'/label/'verification.json')
        retain('feature-'+label,out/'features/asm'/label/filename(wb))
    retain('irq-wb575',out/'irq/wb575/verification.json')
    for label in ['nb','wb']:retain('api-'+label,out/'api'/label/'verification.json')
    name='forced-one-timing.json';save(name,paired());reports.append(name)
    images=[];features=[];c_images=[]
    for label in ['nb8','nb11','wb98','wb128']:
        name='wb.bin' if label.startswith('wb') else 'speex-test.bin'
        paths=[out/'identities'/epoch/label/name for epoch in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,byteIdentical=True,binarySha256=sha(paths[1],False),flashBytes=paths[1].stat().st_size))
    for label,wb in PROFILES.items():
        for backend in ['asm','c']:
            folder=out/'features'/backend/label;meta=json.loads((folder/'backend.json').read_text());symbols=(folder/'symbols.txt').read_text()
            name='wb.bin' if wb else 'speex-test.bin';assert sha(folder/name,False)==meta['binarySha256']
            assert ('speex_avr_forced_innovation_n' in symbols)==(backend=='asm')
            features.append(dict(profile=label,backend=backend,lowRates=meta['lowRates'],selectedBackendVerified=True,
                flashBytes=(folder/name).stat().st_size,binarySha256=meta['binarySha256'],compiledLinkedOnly=backend=='c'))
        folder=out/'c'/label;meta=json.loads((folder/'input.json').read_text());assert meta['backend']=='c' and sha(folder/'player.bin',False)==meta['binarySha256']
        c_images.append(dict(profile=label,compiledLinkedOnly=True,flashBytes=(folder/'player.bin').stat().st_size,binarySha256=meta['binarySha256']))
    name='forced-one-controls.json';save(name,dict(images=images,features=features,cImages=c_images,cDecoderExecuted=False));reports.append(name)
    base=read('forced-zero-admission.json');sources=list(base['sourceSha256'])+ADDED;assert len(sources)==len(set(sources))
    save('forced-one-admission.json',dict(baselineRevision='142df69a',baselineAdmissionSha256=sha(ROOT/'reports/forced-zero-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',backend='explicit AVR ASM',physicalBoardTested=False,
        compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',
        sourceSha256={n:sha(ROOT/n) for n in sources},reportSha256={n:sha(ROOT/'reports'/n) for n in reports},
        limits=['Before raw images/traces may reuse the source/hash-verified parent full admission.',
                'Fresh raw decoding covers NB3.95/WB5.75; IRQ covers WB5.75 with 3% added work.',
                'SPI covers NB3.95 coverage4096 and WB5.75 long2200, continuous history.',
                'Other-profile minimum images are byte-identical; no fresh all-feature other-profile timing claim.',
                'C decoder controls/export compile/link only; isolated C arithmetic executes.',
                'Original pitch/output clamps, Q14 floors, packet formats, state and compact QMF remain unchanged.',
                'ISA simulation only; no physical-board or analog measurements.']))


def audit(args):
    a=read('forced-one-admission.json');base=read('forced-zero-admission.json')
    assert sha(ROOT/'reports/forced-zero-admission.json')==a['baselineAdmissionSha256']
    assert sorted(n for n,v in base['sourceSha256'].items() if sha(ROOT/n)!=v)==sorted(CHANGED)
    for n,v in a['sourceSha256'].items():assert sha(ROOT/n)==v,n
    for n,v in {**base['reportSha256'],**a['reportSha256']}.items():assert sha(ROOT/'reports'/n)==v,n
    for n,v in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==v,n
    b=read('forced-one-baseline-source.json');assert b['sourceTreeVerified'] and b['sourceFiles']==len(base['sourceSha256']) and b['admissionSha256']==a['baselineAdmissionSha256']
    u=read('forced-one-unit.json');assert u['cases']==u['pairedTimingCases']==44059 and u['calleeSavedAndR1Returns']==88118
    assert u['binarySha256']==read('forced-one-unit-image.json')['binarySha256'] and u['uniqueScales']==49 and u['callerScales']==32 and u['randomCases']==8192
    assert u['distinctShapePositions']==640
    for k in ['all32Rows','all20RowPositions','all64Coefficients','counts0Through10','cAsmOriginalAndBigIntExact','exactHistoryAndFlashAddresses',
              'outputNotRead','guardsAndTails','zeroNullPointersAndNoAccess','argumentRegistersPreserved']:assert u[k],k
    assert u['positiveClips'] and u['negativeClips'] and len(u['variable'])==11
    for r in u['variable']:
        assert r['newMuls']==r['calls']*r['count']*6 and r['oldMuls']==r['calls']*r['count']*10
        saving=32*r['count']+35 if r['count'] else 0
        assert r['oldMin']-r['newMin']==r['oldMax']-r['newMax']==saving
    timing=read('forced-one-timing.json')['profiles']
    for label,wb in PROFILES.items():
        old=read('forced-one-before-'+label+'.json');new=read('forced-one-after-'+label+'.json');t=timing[label]
        assert old==read('forced-zero-after-'+label+'.json')
        assert old['frames']==new['frames']==10627 and len(new['streams'])==18
        assert old['binarySha256']==t['beforeBinarySha256'] and new['binarySha256']==t['afterBinarySha256']
        assert new['staticSramBytes']==old['staticSramBytes'] and new['maxCycles']<old['maxCycles']
        assert new['flashBytes']==old['flashBytes']+(224 if wb else 222)
        if wb:assert new['peakStack']==old['peakStack'] and new['freeSram']==old['freeSram']
        else:assert new['minStackPointer']==old['minStackPointer']+13 and new['freeSramAtPeak']==old['freeSramAtPeak']+13
        for r in new['streams']:assert r.get('reset',r.get('resetVerified'))
        assert sum(g['frames'] for g in t['groups'].values())==10627
        assert t['groups']['zero']['frames']==(2223 if wb else 2243)
        assert (t['groups']['zero']['deltaMin'],t['groups']['zero']['deltaMax'])==((0,12) if wb else (0,0))
        assert set(map(int,t['groups']['zero']['deltaCounts']))<=({0,3,6,9,12} if wb else {0})
        assert (t['groups']['nonzero']['deltaMin'],t['groups']['nonzero']['deltaMax'])==((-7881,-6139) if wb else (-7873,-6135))
        assert t['speech']['frames']==6467 and t['speech']['afterMeanCycles']<t['speech']['beforeMeanCycles']
        s=read('forced-one-spi-'+label+'.json');frames=2200 if wb else 4096
        assert s['passed'] and s['frames']==frames and s['s16Exact'] and s['pwmExact'] and s['underruns']==0 and s['includesInterrupts'] and s['fullHistoryWithoutReset']
        assert s['input']['streamBytes']==s['modelStats']['readBytes']==frames*(15 if wb else 10)
        previous=read('forced-zero-spi-'+label+'.json')
        for k in ['pcmSha256','pwmSha256','modelWasmSha256']:assert s[k]==previous[k]
        assert s['input']['inputSha256']==previous['input']['inputSha256'] and s['input']['driverSha256']==previous['input']['driverSha256']
        assert s['minQueuedSamplesBeforeOutput']==(31 if wb else 74) and s['freeSramAtPeak']==(403 if wb else 667)
        assert s['flashBytes']==(26282 if wb else 17788) and s['staticSramBytes']==(1427 if wb else 1251) and s['peakStackBytes']==(218 if wb else 130)
        assert (990 if wb else 1990)<=s['timerIntervalMinCycles']<=s['timerIntervalMaxCycles']<=(1010 if wb else 2010)
        f=read('forced-one-feature-'+label+'.json');assert f['frames']==384 and all(r.get('reset',r.get('resetVerified')) for r in f['streams'])
    q=read('forced-one-irq-wb575.json');assert q['frames']==10627 and q['extraCpuCyclesPerFrame']==9600 and q['includesInterrupts'] and q['underruns']==0
    assert len(q['streams'])==18 and q['minQueuedSamplesBeforeOutput']==22 and q['freeSramAtPeak']==406 and q['flashBytes']==26206 and q['staticSramBytes']==1430
    for old,new in zip(read('forced-zero-irq-wb575.json')['streams'],q['streams']):
        for k in ['stream','frames','inputSha256','pcmSha256']:assert old[k]==new[k]
        assert new['peakStackBytes']==212
    for r in q['streams']:assert r['s16AndPwmExact'] and r['fullHistoryWithoutChunkReset'] and not r['underruns'] and 990<=r['timerIntervalMinCycles']<=r['timerIntervalMaxCycles']<=1010
    for label,zeros,rejected in [('nb',42,6144),('wb',44,7168)]:
        p=read('forced-one-api-'+label+'.json');assert p['frames']==1024 and p['rejectedCalls']==rejected and p['pcmExact'] and p['resetExact']
        z=p['forcedZeroArithmetic'];assert z['frames']==zeros and z['twentyWordCalls']==8*zeros and z['hardwareMultiplies']==652*zeros
        assert z['noAdaptiveKernel'] and z['noExcitationHistoryOrOutputReads'] and z['invalidAndNonzeroCoefficientCallsDoNotExecute']
        f=p['forcedOneArithmetic'];assert f['frames']>0 and f['samples']==160*f['frames'] and f['hardwareMultiplies']==960*f['frames']
        assert f['frames']==(163 if label=='nb' else 161) and f['calls']==(3124 if label=='nb' else 3100)
        assert sum(f['callsByCount'])==f['calls'] and sum(i*n for i,n in enumerate(f['callsByCount']))==f['samples']
        assert f['sixMulsPerSample'] and f['noThreeTapKernelForNb8'] and f['invalidOtherModeAndZeroCoefficientCallsDoNotExecute']
    c=read('forced-one-controls.json');assert len(c['images'])==4 and all(r['byteIdentical'] for r in c['images']) and not c['cDecoderExecuted']
    for image in read('forced-one-layout.json')['images']:
        epoch=image['epoch'];assert image['binarySha256']==read('forced-one-'+epoch+'-wb575.json')['binarySha256']
        assert [r['target'] for r in image['calls']]==['speex_avr_lsp_pair'+str(n) for n in [2,3,4]]
        assert all(r['opcode']==('rcall' if epoch=='before' else 'call') for r in image['calls'])
    assert len(c['features'])==4 and all(r['selectedBackendVerified'] and r['lowRates']==2 for r in c['features'])
    assert all(r['compiledLinkedOnly'] for r in c['features'] if r['backend']=='c') and len(c['cImages'])==2 and all(r['compiledLinkedOnly'] and r['flashBytes']<=32768 for r in c['cImages'])
    e=read('forced-one-export.json');assert e['sources']==21 and not e['handwrittenAssembly'] and not e['duplicateSources']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile'] not in PROFILES:continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:assert sha(args.corpus/row['profile']/folder/(stem+suffix),False)==row[key]
    print('PASS one-tap: 44059 arithmetic cases / 21254 fresh raw / 10627 IRQ / 6296 SPI frames; exact PCM/PWM')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');p.add_argument('--corpus',type=Path);args=p.parse_args()
    if args.record:record()
    audit(args)


if __name__=='__main__':main()
