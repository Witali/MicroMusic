#!/usr/bin/env python3
"""Bind bounded scalar proofs to complete forced-pitch PCM and PWM admission."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHANGED=['src/lowrate_excitation.h','tests/verify_low_api.mjs']
ADDED=['src/forced_math.h','tests/avr_forced_math.c','tests/build_forced_math.py','tests/verify_forced_math.mjs',
       'tests/screen_forced_math.py','tests/build_forced_math_admission.py','tests/run_forced_math_admission.py','tests/audit_forced_math.py']
PROFILES={'nb395':False,'wb575':True}


def sha(path,text=True):
    data=path.read_bytes();return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,data):(ROOT/'reports'/name).write_bytes((json.dumps(data,indent=2)+'\n').encode())
def filename(wb):return 'verification.json' if wb else 'avr-verification.json'


def paired(corpus):
    out=ROOT/'build/forced-math-final';profiles={}
    for label,wb in PROFILES.items():
        traces=[json.loads((out/epoch/label/'forced-zero-timing.json').read_text()) for epoch in ['before','after']]
        assert traces[0]['frames']==traces[1]['frames']==10627 and len(traces[0]['streams'])==len(traces[1]['streams'])==18
        groups={k:dict(frames=0,beforeCycles=0,afterCycles=0,deltaMin=None,deltaMax=None,ancestorSteps=0) for k in ['zero','long','short']}
        speech=dict(frames=0,beforeCycles=0,afterCycles=0);rows=[]
        for old,new in zip(traces[0]['streams'],traces[1]['streams']):
            assert old['stream']==new['stream'] and old['inputSha256']==new['inputSha256'] and old['pcmSha256']==new['pcmSha256']
            assert old['coefficientZero']==new['coefficientZero'] and len(old['cycles'])==len(new['cycles'])==len(old['coefficientZero'])
            raw=(corpus/label/'streams'/old['stream']).read_bytes();width=15 if wb else 10
            assert hashlib.sha256(raw).hexdigest()==old['inputSha256'] and len(raw)==width*len(old['cycles'])
            for i,(zero,a,b) in enumerate(zip(old['coefficientZero'],old['cycles'],new['cycles'])):
                packet=raw[i*width:(i+1)*width];assert packet[0]>>3==8
                code=((packet[3]&3)<<2)|(packet[4]>>6);pitch=17+((packet[2]&1)<<6)+(packet[3]>>2);assert zero==(code==0)
                g=groups['zero' if zero else 'short' if pitch<40 else 'long'];delta=b-a
                g['frames']+=1;g['beforeCycles']+=a;g['afterCycles']+=b
                g['ancestorSteps']+=0 if zero else 4*sum(j//pitch for j in range(40))
                g['deltaMin']=delta if g['deltaMin'] is None else min(g['deltaMin'],delta)
                g['deltaMax']=delta if g['deltaMax'] is None else max(g['deltaMax'],delta)
            row=dict(stream=old['stream'],frames=len(old['cycles']),beforeCycles=sum(old['cycles']),afterCycles=sum(new['cycles']))
            if old['stream'].startswith(('en_','ru_')):
                speech['frames']+=row['frames'];speech['beforeCycles']+=row['beforeCycles'];speech['afterCycles']+=row['afterCycles']
            rows.append(row)
        for epoch in ['before','after']:speech[epoch+'MeanCycles']=speech[epoch+'Cycles']/speech['frames']
        profiles[label]=dict(frames=10627,beforeBinarySha256=traces[0]['binarySha256'],afterBinarySha256=traces[1]['binarySha256'],
            groups=groups,speech=speech,streams=rows)
    return dict(scope='Exact command intervals paired by packet/history; no startup/reset/IRQ',profiles=profiles)


def record(args):
    assert args.corpus,'--record requires the full --corpus'
    out=ROOT/'build/forced-math-final';reports=['forced-math-unit-asm.json','forced-math-unit-c.json']
    def retain(name,path):
        name='forced-math-'+name+'.json';save(name,json.loads(path.read_text()));reports.append(name)
    retain('baseline-source',out/'baseline-source.json');retain('screen',ROOT/'build/forced-math-screen/summary.json')
    retain('corpus',ROOT/'build/forced-zero-screen-data/manifest.json');retain('export',ROOT/'build/low-export-check.json')
    for backend in ['asm','c']:retain('unit-image-'+backend,ROOT/'build/forced-math-unit'/backend/'input.json')
    for label,wb in PROFILES.items():
        for epoch in ['before','after']:retain(epoch+'-'+label,out/epoch/label/filename(wb))
        retain('spi-'+label,out/'spi'/label/'verification.json');retain('feature-'+label,out/'features/asm'/label/filename(wb))
        for variant in ['before','coefficient','q6','both']:
            retain('screen-'+variant+'-'+label,ROOT/'build/forced-math-screen'/variant/label/filename(wb))
    retain('irq-wb575',out/'irq/wb575/verification.json')
    for label in ['nb','wb']:retain('api-'+label,out/'api'/label/'verification.json')
    name='forced-math-timing.json';save(name,paired(args.corpus));reports.append(name)
    images=[];features=[];c_images=[]
    for label in ['nb8','nb11','wb98','wb128']:
        name='wb.bin' if label.startswith('wb') else 'speex-test.bin';paths=[out/'identities'/e/label/name for e in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,byteIdentical=True,flashBytes=paths[1].stat().st_size,binarySha256=sha(paths[1],False)))
    for label,wb in PROFILES.items():
        for backend in ['asm','c']:
            folder=out/'features'/backend/label;meta=json.loads((folder/'backend.json').read_text());name='wb.bin' if wb else 'speex-test.bin'
            assert sha(folder/name,False)==meta['binarySha256'] and meta['backend']==backend and meta['lowRates']==2
            features.append(dict(profile=label,backend=backend,lowRates=2,flashBytes=(folder/name).stat().st_size,
                binarySha256=meta['binarySha256'],compiledLinkedOnly=backend=='c'))
        folder=out/'c'/label;meta=json.loads((folder/'input.json').read_text());assert meta['backend']=='c' and sha(folder/'player.bin',False)==meta['binarySha256']
        c_images.append(dict(profile=label,flashBytes=(folder/'player.bin').stat().st_size,binarySha256=meta['binarySha256'],compiledLinkedOnly=True))
    name='forced-math-controls.json';save(name,dict(images=images,features=features,cImages=c_images,cDecoderExecuted=False));reports.append(name)
    base=read('forced-one-admission.json');sources=list(base['sourceSha256'])+ADDED;assert len(sources)==len(set(sources))
    save('forced-math-admission.json',dict(baselineRevision='3bbca078',prototypeRevision='7e89e352',
        baselineAdmissionSha256=sha(ROOT/'reports/forced-one-admission.json'),
        target='ATmega328P / AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',backend='explicit AVR ASM',
        compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',physicalBoardTested=False,
        sourceSha256={n:sha(ROOT/n) for n in sources},reportSha256={n:sha(ROOT/'reports'/n) for n in reports},
        limits=['Only NB8 arithmetic is connected; submode1 coefficient use remains unchanged.',
                'Fresh full ASM decoding covers NB3.95/WB5.75; before images/traces reuse verified parent admission.',
                'WB5.75 ready-RAM IRQ adds 9600 cycles/frame; SPI tests have no added load.',
                'Four minimum images without NB8 stay byte-identical; no fresh all-feature other-mode timing claim.',
                'C decoder controls/export compile/link only; isolated scalar C arithmetic executes.',
                'Packet formats, state, pitch/output clamps, original rounding and compact QMF remain unchanged.',
                'ISA simulation only; no physical-board or analog measurement.']))


def audit(args):
    a=read('forced-math-admission.json');base=read('forced-one-admission.json')
    assert sha(ROOT/'reports/forced-one-admission.json')==a['baselineAdmissionSha256']
    assert sorted(n for n,h in base['sourceSha256'].items() if sha(ROOT/n)!=h)==sorted(CHANGED)
    for n,h in a['sourceSha256'].items():assert sha(ROOT/n)==h,n
    for n,h in {**base['reportSha256'],**a['reportSha256']}.items():assert sha(ROOT/'reports'/n)==h,n
    for n,h in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==h,n
    b=read('forced-math-baseline-source.json');assert b['sourceTreeVerified'] and b['sourceFiles']==len(base['sourceSha256']) and b['admissionSha256']==a['baselineAdmissionSha256']
    for backend in ['asm','c']:
        u=read('forced-math-unit-'+backend+'.json');im=read('forced-math-unit-image-'+backend+'.json')
        assert u['binarySha256']==im['binarySha256'] and u['backend']==im['backend']==backend and u['structuredCases']==9856 and u['randomCases']==8192
        assert u['all16CoefficientCodes'] and u['all64Q6Coefficients'] and u['originalAndCAndIndependentExact'] and u['negativeTiesPreserved']
        assert u['selectedAliasesExplicitC']==(backend=='c') and u['exhaustiveCases']==(4194304 if backend=='asm' else 0)
        assert u['checkedCalleeSavedReturns']==(33696 if backend=='asm' else 29600) and u['checkedR1Returns']==(4223904 if backend=='asm' else 29600)
        if backend=='asm':assert u['statistics'][0]['minCycles']==u['statistics'][0]['maxCycles']==24 and u['statistics'][0]['muls']==2*u['statistics'][0]['calls']
        assert u['statistics'][3]['minCycles']==u['statistics'][3]['maxCycles']==17 and u['statistics'][4]['minCycles']==u['statistics'][4]['maxCycles']==154
    screen=read('forced-math-screen.json');assert screen['baselineSourceVerified'] and len(screen['rows'])==8
    for label,wb in PROFILES.items():
        old=read('forced-math-before-'+label+'.json');new=read('forced-math-after-'+label+'.json');t=read('forced-math-timing.json')['profiles'][label]
        assert old==read('forced-one-after-'+label+'.json') and old['frames']==new['frames']==10627 and len(new['streams'])==18
        assert old['binarySha256']==t['beforeBinarySha256'] and new['binarySha256']==t['afterBinarySha256']
        assert new['flashBytes']==old['flashBytes']-88 and new['staticSramBytes']==old['staticSramBytes'] and new['maxCycles']<old['maxCycles']
        if wb:assert new['peakStack']==old['peakStack'] and new['freeSram']==old['freeSram']
        else:assert new['minStackPointer']==old['minStackPointer'] and new['freeSramAtPeak']==old['freeSramAtPeak']
        assert all(r.get('reset',r.get('resetVerified')) for r in new['streams'])
        assert sum(g['frames'] for g in t['groups'].values())==10627 and t['groups']['zero']['frames']==(2223 if wb else 2243)
        assert t['speech']['frames']==6467 and t['speech']['afterMeanCycles']<t['speech']['beforeMeanCycles']
        assert t['groups']['zero']['deltaMin']==t['groups']['zero']['deltaMax']==5
        assert (t['groups']['long']['deltaMin'],t['groups']['long']['deltaMax'])==(-279,-277)
        assert (t['groups']['short']['deltaMin'],t['groups']['short']['deltaMax'])==(-2963,-409)
        assert t['groups']['short']['frames']==(2094 if wb else 2121) and t['groups']['short']['ancestorSteps']==(82592 if wb else 82672)
        rows={r['variant']:r for r in screen['rows'] if r['profile']==label}
        assert rows['both']['sourceSha256']==sha(ROOT/'src/lowrate_excitation.h') and rows['both']['binarySha256']==new['binarySha256']
        assert rows['both']['meanCycles']<min(rows['coefficient']['meanCycles'],rows['q6']['meanCycles'])<rows['before']['meanCycles']
        for name,r in rows.items():
            report=read('forced-math-screen-'+name+'-'+label+'.json');assert report['frames']==384 and report['binarySha256']==r['binarySha256'] and r['pcmExact'] and r['resetExact']
        s=read('forced-math-spi-'+label+'.json');previous=read('forced-one-spi-'+label+'.json');frames=2200 if wb else 4096
        assert s['passed'] and s['frames']==frames and s['s16Exact'] and s['pwmExact'] and not s['underruns'] and s['includesInterrupts'] and s['fullHistoryWithoutReset']
        for k in ['pcmSha256','pwmSha256','modelWasmSha256']:assert s[k]==previous[k]
        assert s['input']['inputSha256']==previous['input']['inputSha256'] and s['input']['driverSha256']==previous['input']['driverSha256']
        assert s['input']['streamBytes']==s['modelStats']['readBytes']==frames*(15 if wb else 10)
        assert s['freeSramAtPeak']>=previous['freeSramAtPeak'] and s['minQueuedSamplesBeforeOutput']>=previous['minQueuedSamplesBeforeOutput']
        assert s['flashBytes']==(26194 if wb else 17698) and s['staticSramBytes']==previous['staticSramBytes'] and s['peakStackBytes']==previous['peakStackBytes']
        assert s['minQueuedSamplesBeforeOutput']==(33 if wb else 74)
        assert (990 if wb else 1990)<=s['timerIntervalMinCycles']<=s['timerIntervalMaxCycles']<=(1010 if wb else 2010)
        f=read('forced-math-feature-'+label+'.json');assert f['frames']==384 and all(r.get('reset',r.get('resetVerified')) for r in f['streams'])
    q=read('forced-math-irq-wb575.json');assert q['frames']==10627 and len(q['streams'])==18 and q['extraCpuCyclesPerFrame']==9600 and q['includesInterrupts'] and not q['underruns']
    assert q['minQueuedSamplesBeforeOutput']==25 and q['freeSramAtPeak']==406 and q['flashBytes']==26110 and q['staticSramBytes']==1430
    for old,new in zip(read('forced-one-irq-wb575.json')['streams'],q['streams']):
        for k in ['stream','frames','inputSha256','pcmSha256']:assert old[k]==new[k]
        assert new['s16AndPwmExact'] and new['fullHistoryWithoutChunkReset'] and not new['underruns'] and 990<=new['timerIntervalMinCycles']<=new['timerIntervalMaxCycles']<=1010
    for label,zeros,rejected,nonzeros in [('nb',42,6144,163),('wb',44,7168,161)]:
        p=read('forced-math-api-'+label+'.json');assert p['frames']==1024 and p['rejectedCalls']==rejected and p['pcmExact'] and p['resetExact']
        z=p['forcedZeroArithmetic'];assert z['frames']==zeros and z['twentyWordCalls']==8*zeros and z['hardwareMultiplies']==652*zeros and z['noExcitationHistoryOrOutputReads']
        one=p['forcedOneArithmetic'];assert one['frames']==nonzeros and one['hardwareMultiplies']==960*nonzeros and one['samples']==160*nonzeros
        v=p['forcedQ6Arithmetic'];assert v['calls']==(3148 if label=='nb' else 3172) and v['cycles']==18*v['calls'] and v['hardwareMultiplies']==2*v['calls']
        for k in ['twoMulsPerCall','exactDuringDecoder','inputRegistersAndR1Preserved','exactAncestryCounts','invalidOtherModeAndZeroCoefficientCallsDoNotExecute']:assert v[k],k
    controls=read('forced-math-controls.json');assert not controls['cDecoderExecuted'] and len(controls['images'])==4 and all(r['byteIdentical'] for r in controls['images'])
    assert len(controls['features'])==4 and all(r['lowRates']==2 for r in controls['features']) and all(r['compiledLinkedOnly'] for r in controls['features'] if r['backend']=='c')
    assert len(controls['cImages'])==2 and all(r['compiledLinkedOnly'] and r['flashBytes']<=32768 for r in controls['cImages'])
    e=read('forced-math-export.json');assert e['sources']==21 and not e['handwrittenAssembly'] and not e['duplicateSources']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile'] not in PROFILES:continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:assert sha(args.corpus/row['profile']/folder/(stem+suffix),False)==row[key]
    print('PASS bounded forced math: 4194304 exhaustive scalar pairs / 21254 fresh raw / 10627 IRQ / 6296 SPI frames; exact PCM/PWM')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');p.add_argument('--corpus',type=Path);args=p.parse_args()
    if args.record:record(args)
    audit(args)


if __name__=='__main__':main()
