#!/usr/bin/env python3
"""Retain source-bound HB1 scalar evidence, including verified identical-binary reuse."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct

ROOT=Path(__file__).resolve().parents[1]


def sha(path,text=False):
    data=path.read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8') if text else path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def store(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def body(folder,name):
    functions=list(re.finditer(r'^([0-9a-f]+) <([^>]+)>:',(folder/'disassembly.txt').read_text(encoding='utf-8'),re.M))
    index=next(i for i,m in enumerate(functions) if m[2]==name)
    start=int(functions[index][1],16);end=int(functions[index+1][1],16)
    return (folder/'unit.bin').read_bytes()[start:end]


def adopt(candidate,out):
    """Reuse scalar results only after comparing the complete rebuilt firmware."""
    for backend in ['asm','c','generic']:
        old=candidate/'build/wb-ratio-unit'/backend;new=out/backend
        assert (old/'unit.bin').read_bytes()==(new/'unit.bin').read_bytes(),backend
    old=candidate/'build/wb-ratio-unit/asm'
    report=load(old/'verification-irq.json')
    assert report['allValidatedHbDivisors'] and report['cases']==106727
    shutil.copyfile(old/'verification-irq.json',out/'asm/verification-full-irq.json')
    shutil.copyfile(old/'input.json',out/'asm/full-origin-input.json')
    store(out/'asm/full-reuse.json',dict(mode='Reused by verified identical complete fixture firmware',
        binarySha256=sha(out/'asm/unit.bin'),originalReportSha256=sha(old/'verification-irq.json'),
        originalInputSha256=sha(old/'input.json'),runtimeResultsChanged=False))
    experiment=candidate.parent
    for name in ['unit.bin','input.json','symbols.txt','disassembly.txt']:
        target=out/'reference/generic-baseline'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(experiment/'baseline/build/wb-ratio-unit/asm'/name,target)
    target=out/'replay/actual-all.json';target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(experiment/'actual-all.json',target)
    for profile in ['wb395','wb575','wb775','wb98','wb128']:
        target=out/'replay/capture'/f'{profile}.json';target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(experiment/'capture'/profile/'captured.json',target)
    shutil.copyfile(experiment/'comparison-actual.json',out/'reference/unroll-tradeoffs.json')
    print('Adopted scalar evidence after complete firmware identity checks; run named replay checks next')


def report_summary(report):
    keys=['backend','cases','divisorsSwept','boundaryCases','coefficientDerivedCases',
        'allValidatedHbDivisors','validatedHbDivisorBounds','negativeRoundedNumerators',
        'saturatedCases','zeroQuotients','independentBigIntExact','explicitBackendSelectionVerified',
        'calleeSavedAndR1Returns','stats','includesInterrupts','completedTimerInterrupts',
        'timerCompareEvents','noLostTimerInterrupts','peakStack']
    return {key:report[key] for key in keys if key in report}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit',type=Path,default=ROOT/'build/wb-hb-ratio-unit')
    parser.add_argument('--adopt-candidate',type=Path)
    parser.add_argument('--refresh-domain-proof',action='store_true',help='Refresh only the independent domain-proof metadata')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args();out=args.unit
    proof=load(ROOT/'reports/wb-response-domain.json');proof_hash=sha(ROOT/'reports/wb-response-domain.json',True)
    assert proof['currentPrimitiveMatchesSource'] and proof['untouchedXiphComparisons']==25171968
    assert (proof['responseMin'],proof['responseMax'])==(111,31849)
    assert proof['modular16ResponseExact'] and not proof['cDecoderExecuted']
    for path,h in proof['sourceSha256'].items():assert sha(ROOT/path,True)==h,path
    if args.refresh_domain_proof:
        for label in ['asm','c','generic','generic-control']:
            path=out/label/'input.json';meta=load(path)
            assert sha(out/label/'unit.bin')==meta['binarySha256']
            meta['hbDomainProofSha256']=proof_hash;store(path,meta)
    if args.adopt_candidate:
        adopt(args.adopt_candidate,out);return

    images={};metas={}
    for label in ['asm','c','generic','generic-control']:
        folder=out/label;meta=load(folder/'input.json');metas[label]=meta
        assert sha(folder/'unit.bin')==meta['binarySha256']
        assert meta['hbDomainProofSha256']==proof_hash
        for path,h in meta['sourceSha256'].items():assert sha(ROOT/path,True)==h,path
        report_path=folder/('verification-irq.json' if label=='generic-control' else 'verification-quick-irq.json')
        report=load(report_path)
        assert report['binarySha256']==meta['binarySha256'] and report['sourceSha256']==meta['sourceSha256']
        for key in ['independentBigIntExact','explicitBackendSelectionVerified','noLostTimerInterrupts']:
            assert report[key] is True
        assert report['completedTimerInterrupts']==report['timerCompareEvents']>0
        assert report['cases']==(4403 if label=='generic-control' else 1862)
        symbols=(folder/'symbols.txt').read_text(encoding='utf-8')
        if label=='generic-control':assert 'speex_wb_ratio_hb_div_avr' not in symbols
        else:
            assert 'speex_wb_ratio_div_avr' not in symbols and 'speex_wb_gain_div_avr' not in symbols
            assert len(body(folder,'speex_wb_ratio_hb_div_avr'))==306
        images[label]=dict(binarySha256=meta['binarySha256'],reportSha256=sha(report_path),results=report_summary(report))
    assert metas['c']['binarySha256']==metas['generic']['binarySha256']
    for meta in metas.values():
        assert meta['toolSha256']==metas['asm']['toolSha256']
        assert meta['deviceHeadersSha256']==metas['asm']['deviceHeadersSha256']

    full=load(out/'asm/verification-full-irq.json')
    assert full['binarySha256']==metas['asm']['binarySha256']
    assert full['cases']==106727 and full['allValidatedHbDivisors'] and full['divisorsSwept']==31739
    assert full['boundaryCases']==1510 and full['coefficientDerivedCases']==10000
    assert full['calleeSavedAndR1Returns']==213454
    assert full['completedTimerInterrupts']==full['timerCompareEvents']==304939 and full['noLostTimerInterrupts']
    reuse_path=out/'asm/full-reuse.json'
    if reuse_path.exists():
        reuse=load(reuse_path);origin=load(out/'asm/full-origin-input.json')
        assert reuse['binarySha256']==metas['asm']['binarySha256']==origin['binarySha256']
        assert reuse['originalReportSha256']==sha(out/'asm/verification-full-irq.json')
        assert reuse['originalInputSha256']==sha(out/'asm/full-origin-input.json')
        assert full['sourceSha256']==origin['sourceSha256'] and not reuse['runtimeResultsChanged']
    else:
        assert full['sourceSha256']==metas['asm']['sourceSha256']
        reuse=dict(mode='Fresh full run of the current compiled fixture')

    parent=load(ROOT/'reports/wb-ratio-unit.json');baseline=out/'reference/generic-baseline'
    assert sha(baseline/'unit.bin')==parent['images']['asm']['binarySha256']
    old_body=body(baseline,'speex_wb_ratio_div_avr')
    assert len(old_body)==72 and old_body==body(out/'generic-control','speex_wb_ratio_div_avr')
    vectors=load(out/'replay/actual-all.json')['captured'];assert len(vectors)==15076
    results={};timings={}
    for label in ['asm-replay','generic-control-replay']:
        folder=out/label;meta=load(folder/'input.json');report=load(folder/'verification-replay-irq.json')
        assert report['binarySha256']==meta['binarySha256'] and report['cases']==len(vectors)
        assert report['replayInputSha256']==sha(out/'replay/actual-all.json')
        assert report['independentBigIntExact'] and report['noLostTimerInterrupts']
        assert report['sourceSha256']==meta['sourceSha256']
        timing_path=folder/'timing-replay-irq.bin';raw_timing=timing_path.read_bytes()
        assert len(raw_timing)==4*len(vectors),'Exactly two uint16 cycle counts per replay case'
        values=[word[0] for word in struct.iter_unpack('<H',raw_timing)]
        assert len(values)==2*len(vectors)
        raw_values=values[0::2];selected_values=values[1::2]
        raw_total=sum(raw_values);selected_total=sum(selected_values)
        groups=report['timingGroups'];selected_stats=report['stats']['selected'];asm_stats=report['stats']['asm']
        assert sum(group['cases'] for group in groups.values())==len(vectors)
        assert raw_total==sum(group['asmTotal'] for group in groups.values()),'Raw scalar timing total'
        assert selected_total==sum(group['selectedTotal'] for group in groups.values()),'Grouped selected timing total'
        assert selected_stats['calls']==len(vectors) and selected_total==selected_stats['totalCycles']
        assert asm_stats['calls']==2*len(vectors),'Direct and selected ASM calls per replay case'
        assert (min(raw_values),max(raw_values))==(asm_stats['minCycles'],asm_stats['maxCycles'])
        assert (min(selected_values),max(selected_values))==(selected_stats['minCycles'],selected_stats['maxCycles'])
        results[label]=dict(binarySha256=meta['binarySha256'],reportSha256=sha(folder/'verification-replay-irq.json'),
            timingSha256=sha(timing_path),timingBytes=len(raw_timing),
            timingEncoding='Little-endian uint16 pairs: raw ASM, selected wrapper',
            rawCyclesTotal=raw_total,selectedCyclesTotal=selected_total,
            timingTotalsReconciled=True,results=report_summary(report));timings[label]=values
    before=timings['generic-control-replay'];after=timings['asm-replay']
    deltas=[after[i]-before[i] for i in range(1,len(before),2)]
    assert all(deltas[i//2]==after[i]-before[i]-8 for i in range(0,len(before),2))
    profiles=[];offset=0;merged=[]
    for profile in ['wb395','wb575','wb775','wb98','wb128']:
        path=out/'replay/capture'/f'{profile}.json';capture=load(path);count=4*capture['frames']
        merged.extend(capture['captured']);delta=deltas[offset:offset+count];offset+=count
        frames=[-sum(delta[i:i+4]) for i in range(0,len(delta),4)]
        profiles.append(dict(profile=profile,frames=capture['frames'],sourceImageSha256=capture['binarySha256'],
            captureSha256=sha(path),meanScalarCallerSavingPerFrame=-sum(delta)/capture['frames'],
            minScalarFrameSaving=min(frames),maxScalarFrameSaving=max(frames)))
    assert merged==vectors
    paths=['src/wb_gain_div.h','src/wb_gain_div.S','src/speex_platform.h',
        'tests/avr_wb_hb_ratio.c','tests/build_wb_hb_ratio.py','tests/verify_wb_hb_ratio.mjs',
        'tests/capture_wb_hb_ratio.mjs','tests/audit_wb_hb_ratio.py','tests/avr_wb_ratio.c',
        'tests/verify_wb_ratio.mjs','tests/avr_tick.mjs','package.json','package-lock.json']
    receipt=dict(scope='Validated-HB1 scalar/C fallback/ABI/IRQ evidence and scalar replay only; whole-firmware admission is separate',
        target='ATmega328P / classic AVR5 / GNU ABI',compiler=metas['asm']['compiler'],simulator='avr8js 0.21.1',
        sourceHashMode='UTF-8 text normalized to LF',sourceSha256={p:sha(ROOT/p,True) for p in paths},
        hbDomainProofSha256=proof_hash,genericParentReceiptSha256=sha(ROOT/'reports/wb-ratio-unit.json',True),
        toolSha256=metas['asm']['toolSha256'],deviceHeadersSha256=metas['asm']['deviceHeadersSha256'],
        domain=dict(low=[1,335949],high=[111,31849],roundedNumerator=[183,43017396],shiftedRemainderMax=63697),
        privateAsmBytes=306,genericAsmBytes=72,genericAsmBodySha256=hashlib.sha256(old_body).hexdigest(),
        functionSectionGcBothDirectionsVerified=True,localStackBytes=0,persistentDataBytes=0,
        normalAsmCycles='138 + popcount(quotient)',saturationAsmCycles=16,
        cycleScope='Entry through RET, excluding IRQ entry/instructions; selected wrappers include rounding/setup',
        fullDomain=dict(reportSha256=sha(out/'asm/verification-full-irq.json'),binding=reuse,results=report_summary(full)),
        currentQuickIrq=images,cAndForcedGenericBinariesIdentical=True,
        actualReplay=dict(inputSha256=sha(out/'replay/actual-all.json'),calls=len(vectors),frames=3769,
            before=results['generic-control-replay'],after=results['asm-replay'],profiles=profiles,
            meanScalarCallerSavingPerFrame=-sum(deltas)/3769),
        measuredBroadDomainUnrollTradeoffs=load(out/'reference/unroll-tradeoffs.json'),
        physicalBoardTested=False,cDecoderExecuted=False)
    serialized=json.dumps(receipt,indent=2)+'\n'
    assert not re.search(r'(?:[A-Za-z]:[\\/]|/home/|/Users/|/mnt/|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})',serialized)
    target=ROOT/'reports/wb-hb-ratio-unit.json'
    if args.check:assert load(target)==receipt,'Stale validated-HB1 scalar receipt'
    else:target.write_text(serialized,encoding='utf-8')
    print('PASS validated-HB1 scalar receipt: source bindings, complete domain, C selection, GC and matched replay')


if __name__=='__main__':main()
