#!/usr/bin/env python3
"""Audit exact finite NB1 gain composition and matched full output evidence."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CHANGED=['src/lowrate_excitation.h','tests/verify_avr.mjs','tests/verify_wb.mjs','tests/verify_low_api.mjs']
ADDED=['src/nb1_gain.h','tests/avr_nb1_gain.c','tests/build_nb1_gain.py','tests/verify_nb1_gain.mjs',
       'tests/screen_nb1_gain.py','tests/build_nb1_gain_admission.py','tests/run_nb1_gain_admission.py','tests/audit_nb1_gain.py']
PROFILES={'nb215':False,'wb395':True}


def sha(path,text=True):
    data=path.read_bytes();return hashlib.sha256(data.replace(b'\r\n',b'\n') if text else data).hexdigest()


def read(name):return json.loads((ROOT/'reports'/name).read_text())
def save(name,data):(ROOT/'reports'/name).write_bytes((json.dumps(data,indent=2)+'\n').encode())
def filename(wb):return 'verification.json' if wb else 'avr-verification.json'


def paired(corpus):
    out=ROOT/'build/nb1-gain-final';profiles={}
    for label,wb in PROFILES.items():
        traces=[json.loads((out/e/label/'packet-timing.json').read_text()) for e in ['before','after']]
        assert all(t['frames']==10627 and len(t['streams'])==18 for t in traces)
        codes=[dict(code=k,frames=0,beforeCycles=0,afterCycles=0,deltaMin=None,deltaMax=None) for k in range(16)]
        speech=dict(frames=0,beforeCycles=0,afterCycles=0,codeHistogram=[0]*16);rows=[]
        for a,b in zip(traces[0]['streams'],traces[1]['streams']):
            for k in ['stream','inputSha256','pcmSha256']:assert a[k]==b[k]
            assert len(a['cycles'])==len(b['cycles']);raw=(corpus/label/'streams'/a['stream']).read_bytes();width=10 if wb else 6
            assert hashlib.sha256(raw).hexdigest()==a['inputSha256'] and len(raw)==width*len(a['cycles'])
            histogram=[0]*16
            for i,(x,y) in enumerate(zip(a['cycles'],b['cycles'])):
                p=i*width;assert raw[p]>>3==1;k=((raw[p+3]&3)<<2)|(raw[p+4]>>6);g=codes[k];d=y-x
                g['frames']+=1;g['beforeCycles']+=x;g['afterCycles']+=y
                histogram[k]+=1
                g['deltaMin']=d if g['deltaMin'] is None else min(g['deltaMin'],d)
                g['deltaMax']=d if g['deltaMax'] is None else max(g['deltaMax'],d)
            row=dict(stream=a['stream'],frames=len(a['cycles']),beforeCycles=sum(a['cycles']),afterCycles=sum(b['cycles']))
            if a['stream'].startswith(('en_','ru_')):
                speech['frames']+=row['frames'];speech['beforeCycles']+=row['beforeCycles'];speech['afterCycles']+=row['afterCycles']
                speech['codeHistogram']=[x+y for x,y in zip(speech['codeHistogram'],histogram)]
            rows.append(row)
        for e in ['before','after']:speech[e+'MeanCycles']=speech[e+'Cycles']/speech['frames']
        speech['zeroGainFrames']=sum(speech['codeHistogram'][:4])
        profiles[label]=dict(frames=10627,beforeBinarySha256=traces[0]['binarySha256'],afterBinarySha256=traces[1]['binarySha256'],
            codeGroups=codes,speech=speech,streams=rows)
    return dict(scope='Exact paired full-history command intervals; no IRQ, startup or reset',profiles=profiles)


def record(args):
    assert args.corpus,'--record requires --corpus'
    out=ROOT/'build/nb1-gain-final';reports=[]
    def retain(name,path):
        name='nb1-gain-'+name+'.json';save(name,json.loads(path.read_text()));reports.append(name)
    retain('baseline-source',out/'baseline-source.json');retain('screen',ROOT/'build/nb1-gain-screen/summary.json')
    retain('corpus',ROOT/'build/nb1-gain-screen-data/manifest.json');retain('export',ROOT/'build/low-export-check.json')
    for backend in ['asm','c']:
        retain('unit-'+backend,ROOT/'build/nb1-gain-unit'/backend/'verification.json')
        retain('unit-image-'+backend,ROOT/'build/nb1-gain-unit'/backend/'input.json')
    for epoch in ['before','after']:
        for label,wb in PROFILES.items():
            retain(epoch+'-'+label,out/epoch/label/filename(wb))
            retain(epoch+'-spi-'+label,out/epoch/'spi'/label/'verification.json')
        for name in ['irq8','irq11']:retain(epoch+'-'+name,out/epoch/name/'verification.json')
        for label in ['nb','wb']:retain(epoch+'-api-'+label,out/epoch/'api'/label/'verification.json')
    for label,wb in PROFILES.items():
        retain('feature-'+label,out/'features/asm'/label/filename(wb))
        for variant in ['before','coefficient','factored','table','bounded-table','selected']:
            retain('screen-'+variant+'-'+label,ROOT/'build/nb1-gain-screen'/variant/label/filename(wb))
    name='nb1-gain-timing.json';save(name,paired(args.corpus));reports.append(name)
    images=[];features=[];c_images=[]
    for label in ['nb8','nb11','wb98','wb128','nb395','wb575']:
        name='wb.bin' if label.startswith('wb') else 'speex-test.bin';paths=[out/'identities'/e/label/name for e in ['before','after']]
        assert paths[0].read_bytes()==paths[1].read_bytes(),label
        images.append(dict(profile=label,byteIdentical=True,flashBytes=paths[1].stat().st_size,binarySha256=sha(paths[1],False)))
    for label,wb in PROFILES.items():
        for backend in ['asm','c']:
            folder=out/'features'/backend/label;meta=json.loads((folder/'backend.json').read_text());name='wb.bin' if wb else 'speex-test.bin'
            assert sha(folder/name,False)==meta['binarySha256'] and meta['backend']==backend and meta['lowRates']==4
            symbols=(folder/'symbols.txt').read_text();assert symbols.count('speex_nb1_gain_table')==1
            features.append(dict(profile=label,backend=backend,lowRates=4,flashBytes=(folder/name).stat().st_size,
                binarySha256=meta['binarySha256'],oneGainTable=True,compiledLinkedOnly=backend=='c'))
        folder=out/'c'/label;meta=json.loads((folder/'input.json').read_text());assert meta['backend']=='c' and sha(folder/'player.bin',False)==meta['binarySha256']
        c_images.append(dict(profile=label,flashBytes=(folder/'player.bin').stat().st_size,binarySha256=meta['binarySha256'],compiledLinkedOnly=True))
    name='nb1-gain-controls.json';save(name,dict(images=images,features=features,cImages=c_images,cDecoderExecuted=False));reports.append(name)
    base=read('forced-math-admission.json');sources=list(base['sourceSha256'])+ADDED;assert len(sources)==len(set(sources))
    save('nb1-gain-admission.json',dict(baselineRevision='4b45b0e4',baselineAdmissionSha256=sha(ROOT/'reports/forced-math-admission.json'),
        target='ATmega328P / classic AVR5 / 16 MHz / 2 KB SRAM / GNU ABI',backend='explicit AVR ASM with portable C gain lookup',
        compiler='AVR GCC 7.3.0; existing Os/O2/O3, LTO, mcall-prologues and mrelax',physicalBoardTested=False,
        sourceSha256={n:sha(ROOT/n) for n in sources},reportSha256={n:sha(ROOT/'reports'/n) for n in reports},
        limits=['Exact finite composition replaces both original NB1 quantizers/clamps; no new arithmetic ASM.',
                'Fresh before/after NB2.15 and WB3.95 cover 42508 matched raw frames and full resets.',
                'Fresh before/after WB3.95 IRQ at +8% and +11% covers 42508 frames.',
                'Fresh paired continuous SPI covers NB2.15 long6000 and WB3.95 long3600 without added load.',
                'Six images with NB1 disabled remain byte-identical; no fresh all-feature other-mode timing claim.',
                'Full C decoder controls/export compile/link only; isolated C scalar primitives execute.',
                'Packet format, gain values, original rounding, state, delays and compact QMF remain unchanged.',
                'ISA simulation only; no physical-board or analog measurement.']))


def audit(args):
    a=read('nb1-gain-admission.json');base=read('forced-math-admission.json')
    assert sha(ROOT/'reports/forced-math-admission.json')==a['baselineAdmissionSha256']
    assert sorted(n for n,h in base['sourceSha256'].items() if sha(ROOT/n)!=h)==sorted(CHANGED)
    for n,h in a['sourceSha256'].items():assert sha(ROOT/n)==h,n
    for n,h in {**base['reportSha256'],**a['reportSha256']}.items():assert sha(ROOT/'reports'/n)==h,n
    for n,h in read('spi-input-admission.json')['sourceSha256'].items():assert sha(ROOT.parents[2]/n)==h,n
    b=read('nb1-gain-baseline-source.json');assert b['sourceTreeVerified'] and b['sourceFiles']==len(base['sourceSha256']) and b['admissionSha256']==a['baselineAdmissionSha256']
    expected=[];coefficients=[]
    for code in range(16):
        c=(2185*(code<<6)+16384)>>15;coefficients.append(c);expected.append(max(0,min(64,(24576*(c-13)+8192)>>14)))
    for backend in ['asm','c']:
        u=read('nb1-gain-unit-'+backend+'.json');im=read('nb1-gain-unit-image-'+backend+'.json')
        assert u['backend']==im['backend']==backend and u['binarySha256']==im['binarySha256']==read('nb1-gain-unit-asm.json')['binarySha256']
        assert u['coefficients']==coefficients and u['gains']==expected and coefficients[15]==64
        for k in ['all16Codes','originalNarrowAndFactoredAndTableExact','code15Coefficient64','tableInFlash','exactFlashAddresses','lookupHasNoMuls']:assert u[k],k
        assert u['calleeSavedAndR1Returns']==80 and len(u['statistics'])==5
        for i,s in enumerate(u['statistics']):
            assert s['calls']==16 and s['muls']==[144,96,32,0,0][i] and s['lpm']==(16 if i>=3 else 0)
        assert u['statistics'][3]['minCycles']==u['statistics'][3]['maxCycles']==11 and u['statistics'][4]['minCycles']==u['statistics'][4]['maxCycles']==14
    screen=read('nb1-gain-screen.json');assert screen['baselineSourceVerified'] and len(screen['rows'])==12
    for label,wb in PROFILES.items():
        old=read('nb1-gain-before-'+label+'.json');new=read('nb1-gain-after-'+label+'.json');t=read('nb1-gain-timing.json')['profiles'][label]
        assert old['frames']==new['frames']==10627 and len(old['streams'])==len(new['streams'])==18
        assert old['binarySha256']==t['beforeBinarySha256'] and new['binarySha256']==t['afterBinarySha256']
        assert new['flashBytes']==old['flashBytes']-82 and new['staticSramBytes']==old['staticSramBytes'] and new['maxCycles']==old['maxCycles']-(296 if wb else 312)
        if wb:assert new['peakStack']==old['peakStack'] and new['freeSram']==old['freeSram']
        else:assert new['minStackPointer']==old['minStackPointer'] and new['freeSramAtPeak']==old['freeSramAtPeak']
        assert all(r.get('reset',r.get('resetVerified')) for r in old['streams']+new['streams'])
        assert sum(g['frames'] for g in t['codeGroups'])==10627 and all(g['frames']>0 and g['deltaMax']<0 for g in t['codeGroups'])
        assert t['speech']['frames']==6467 and t['speech']['afterMeanCycles']<t['speech']['beforeMeanCycles']
        assert (min(g['deltaMin'] for g in t['codeGroups']),max(g['deltaMax'] for g in t['codeGroups']))==((-296,-292) if wb else (-312,-308))
        variants={r['variant']:r for r in screen['rows'] if r['profile']==label};selected=variants['selected'];chosen=variants['table' if wb else 'bounded-table']
        assert selected['sourceSha256']==sha(ROOT/'src/lowrate_excitation.h') and selected['binarySha256']==chosen['binarySha256']==new['binarySha256']
        assert selected['meanCycles']==min(r['meanCycles'] for r in variants.values())
        for name,row in variants.items():
            s=read('nb1-gain-screen-'+name+'-'+label+'.json');assert s['frames']==384 and s['binarySha256']==row['binarySha256'] and row['pcmExact'] and row['resetExact']
        for epoch in ['before','after']:
            s=read('nb1-gain-'+epoch+'-spi-'+label+'.json');frames=3600 if wb else 6000
            assert s['passed'] and s['frames']==frames and s['s16Exact'] and s['pwmExact'] and not s['underruns'] and s['includesInterrupts'] and s['fullHistoryWithoutReset']
            assert s['input']['streamBytes']==s['modelStats']['readBytes']==36000
            assert (990 if wb else 1990)<=s['timerIntervalMinCycles']<=s['timerIntervalMaxCycles']<=(1010 if wb else 2010)
        before=read('nb1-gain-before-spi-'+label+'.json');after=read('nb1-gain-after-spi-'+label+'.json')
        for k in ['pcmSha256','pwmSha256','modelWasmSha256']:assert before[k]==after[k]
        for k in ['inputSha256','driverSha256']:assert before['input'][k]==after['input'][k]
        assert after['flashBytes']==before['flashBytes']-82 and after['staticSramBytes']==before['staticSramBytes'] and after['peakStackBytes']==before['peakStackBytes']
        assert after['freeSramAtPeak']==before['freeSramAtPeak']==(407 if wb else 669)
        assert after['minQueuedSamplesBeforeOutput']==before['minQueuedSamplesBeforeOutput']==(30 if wb else 74)
        f=read('nb1-gain-feature-'+label+'.json');assert f['frames']==384 and all(r.get('reset',r.get('resetVerified')) for r in f['streams'])
    for name,load in [('irq8',25600),('irq11',35200)]:
        old,new=[read('nb1-gain-'+e+'-'+name+'.json') for e in ['before','after']]
        for q in [old,new]:
            assert q['frames']==10627 and len(q['streams'])==18 and q['extraCpuCyclesPerFrame']==load and q['includesInterrupts'] and not q['underruns']
            for r in q['streams']:assert r['s16AndPwmExact'] and r['fullHistoryWithoutChunkReset'] and not r['underruns'] and 990<=r['timerIntervalMinCycles']<=r['timerIntervalMaxCycles']<=1010
        assert new['flashBytes']==old['flashBytes']-82==26028 and new['staticSramBytes']==old['staticSramBytes']==1425
        assert new['freeSramAtPeak']==old['freeSramAtPeak']==410 and new['minQueuedSamplesBeforeOutput']==old['minQueuedSamplesBeforeOutput']==(30 if name=='irq8' else 22)
        for x,y in zip(old['streams'],new['streams']):
            for k in ['stream','frames','inputSha256','pcmSha256']:assert x[k]==y[k]
    for label,rejected in [('nb',6144),('wb',7168)]:
        old,new=[read('nb1-gain-'+e+'-api-'+label+'.json') for e in ['before','after']]
        for p in [old,new]:assert p['frames']==1024 and p['rejectedCalls']==rejected and p['pcmExact'] and p['resetExact']
        assert old['inputSha256']==new['inputSha256'] and old['pcmSha256']==new['pcmSha256']
        g=new['nb1GainLookup'];assert g['calls']==sum(g['codeHistogram'])==new['framePreparationArithmetic']['calls']==old['framePreparationArithmetic']['calls']
        assert g['exactFlashAddressPerFrame'] and g['originalFiniteMapVerified'] and g['invalidAndOtherModeCallsDoNotExecute']
        assert g['calls']==206 and set(old['framePreparationArithmetic']['perCall'])=={104} and set(new['framePreparationArithmetic']['perCall'])=={94}
        assert old['framePreparationArithmetic']['hardwareMultiplies']==21424 and new['framePreparationArithmetic']['hardwareMultiplies']==19364
    c=read('nb1-gain-controls.json');assert not c['cDecoderExecuted'] and len(c['images'])==6 and all(r['byteIdentical'] for r in c['images'])
    assert len(c['features'])==4 and all(r['lowRates']==4 and r['oneGainTable'] for r in c['features']) and all(r['compiledLinkedOnly'] for r in c['features'] if r['backend']=='c')
    assert len(c['cImages'])==2 and all(r['compiledLinkedOnly'] and r['flashBytes']<=32768 for r in c['cImages'])
    e=read('nb1-gain-export.json');assert e['sources']==21 and not e['handwrittenAssembly'] and not e['duplicateSources']
    if args.corpus:
        for row in read('low-final-corpus.json')['streams']:
            if row['profile'] not in PROFILES:continue
            stem=Path(row['stream']).stem
            for folder,suffix,key in [('streams','.spxraw','inputSha256'),('oracle','.pcm','pcmSha256')]:assert sha(args.corpus/row['profile']/folder/(stem+suffix),False)==row[key]
    print('PASS finite NB1 gain: 42508 fresh paired raw / 42508 loaded IRQ / 19200 continuous SPI frames; exact PCM/PWM')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--record',action='store_true');p.add_argument('--corpus',type=Path);args=p.parse_args()
    if args.record:record(args)
    audit(args)


if __name__=='__main__':main()
