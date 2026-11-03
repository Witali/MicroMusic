#!/usr/bin/env python3
"""Audit isolated ratio evidence and retain a path-free, source-bound receipt."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def sha(path,text=False):
    data=path.read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8') if text else path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def rebind_sources(unit):
    """Change only source-hash metadata, with binary/source identity guards."""
    for backend in ['asm','c','generic']:
        folder=unit/backend
        input_path=folder/'input.json'
        meta=json.loads(input_path.read_text(encoding='utf-8'))
        assert sha(folder/'unit.bin')==meta['binarySha256']
        canonical={}
        variants={}
        for path,old in meta['sourceSha256'].items():
            text=(ROOT/path).read_text(encoding='utf-8').replace('\r\n','\n')
            canonical[path]=hashlib.sha256(text.encode('utf-8')).hexdigest()
            variants[path]={canonical[path],sha(ROOT/path),
                hashlib.sha256(text.replace('\n','\r\n').encode('utf-8')).hexdigest()}
            assert old in variants[path],('Source changed beyond line endings',path)
        for report_path in [input_path,*sorted(folder.glob('verification*.json'))]:
            data=json.loads(report_path.read_text(encoding='utf-8'))
            assert data['binarySha256']==meta['binarySha256']
            for path,h in data.get('sourceSha256',{}).items():assert h in variants[path],path
            unchanged={k:v for k,v in data.items() if k not in ['sourceHashMode','sourceSha256']}
            data.update(sourceHashMode='UTF-8 text normalized to LF',sourceSha256=canonical)
            assert unchanged=={k:v for k,v in data.items() if k not in ['sourceHashMode','sourceSha256']}
            report_path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unit',type=Path,default=ROOT/'build/wb-ratio-unit')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--rebind-source-metadata',action='store_true',
        help='Normalize only proven equivalent LF/CRLF source metadata, retaining identical binaries/results')
    args=parser.parse_args()
    if args.rebind_source_metadata:rebind_sources(args.unit)
    images={}
    for backend in ['asm','c','generic']:
        folder=args.unit/backend
        meta=json.loads((folder/'input.json').read_text(encoding='utf-8'))
        assert meta['backend']==backend
        assert sha(folder/'unit.bin')==meta['binarySha256']
        assert meta['sourceHashMode']=='UTF-8 text normalized to LF'
        for path,h in meta['sourceSha256'].items():assert sha(ROOT/path,True)==h,path
        if backend!='asm':
            assert meta['toolSha256']==asm_meta['toolSha256']
            assert meta['deviceHeadersSha256']==asm_meta['deviceHeadersSha256']
            assert meta['compiler']==asm_meta['compiler']
        irq=json.loads((folder/'verification-irq.json').read_text(encoding='utf-8'))
        assert irq['binarySha256']==meta['binarySha256']
        assert irq['sourceHashMode']==meta['sourceHashMode']
        assert irq['sourceSha256']==meta['sourceSha256']
        assert irq['deviceHeadersSha256']==meta['deviceHeadersSha256']
        for flag in ['independentBigIntExact','signed16DivisorHalfCastPreserved',
                     'explicitBackendSelectionVerified','arbitraryCalleeSavedPatterns',
                     'readonlyInputs','includesInterrupts','noLostTimerInterrupts']:
            assert irq[flag] is True,(backend,flag)
        assert irq['completedTimerInterrupts']==irq['timerCompareEvents']>0
        assert irq['physicalBoardTested'] is False
        assert irq['calleeSavedAndR1Returns']==irq['cases']*(2 if backend=='asm' else 1)
        images[backend]=dict(binarySha256=meta['binarySha256'],compilerOptions=meta['options'],
            irqReportSha256=sha(folder/'verification-irq.json'),irq=irq)
        if backend=='asm':
            assert irq['allPositiveDivisors'] is True and irq['divisorsSwept']==270414
            assert irq['cases']==824573 and irq['boundaryCases']==3331 and irq['coefficientDerivedCases']==10000
            bare=json.loads((folder/'verification.json').read_text(encoding='utf-8'))
            assert bare['binarySha256']==meta['binarySha256']
            assert bare['sourceHashMode']==meta['sourceHashMode']
            assert bare['sourceSha256']==meta['sourceSha256']
            assert bare['includesInterrupts'] is False
            for key in ['cases','divisorsSwept','boundaryCases','coefficientDerivedCases',
                        'negativeRoundedNumerators','saturatedCases','zeroQuotients',
                        'stats','calleeSavedAndR1Returns']:
                assert bare[key]==irq[key],key
            images[backend].update(bareReportSha256=sha(folder/'verification.json'),bare=bare)
            asm_meta=meta
    assert images['c']['binarySha256']==images['generic']['binarySha256']
    for backend in ['c','generic']:
        assert images[backend]['irq']['cases']==4403
        assert images[backend]['irq']['allPositiveDivisors'] is False
    disassembly=(args.unit/'asm/disassembly.txt').read_text(encoding='utf-8')
    functions=list(re.finditer(r'^([0-9a-f]+) <([^>]+)>:',disassembly,re.M))
    index=next(i for i,m in enumerate(functions) if m[2]=='speex_wb_ratio_div_avr')
    primitive_bytes=int(functions[index+1][1],16)-int(functions[index][1],16)
    assert primitive_bytes==72
    paths=['src/wb_gain_div.h','src/wb_gain_div.S','src/speex_platform.h',
        'tests/avr_wb_ratio.c','tests/build_wb_ratio.py','tests/verify_wb_ratio.mjs',
        'tests/audit_wb_ratio.py','tests/avr_tick.mjs','package.json','package-lock.json',
        'vendor/speex-1.2.1/libspeex/fixed_generic.h','vendor/speex-1.2.1/COPYING']
    receipt=dict(scope='Isolated bounded LPC-response arithmetic/ABI/Timer2 evidence; no complete C decoder execution or whole-player admission',
        target='ATmega328P / classic AVR5 / GNU ABI',compiler=asm_meta['compiler'],simulator='avr8js 0.21.1',
        sourceHashMode='UTF-8 text normalized to LF',sourceSha256={p:sha(ROOT/p,True) for p in paths},
        sourceMetadataRebinding='Original source-byte input/report metadata was normalized to LF by verified unchanged unit binary hashes; runtime results are unchanged',
        toolSha256=asm_meta['toolSha256'],deviceHeadersSha256=asm_meta['deviceHeadersSha256'],
        domain=dict(lowResponse=[1,335949],highResponse=[1,270414],roundedNumerator=[-16256,43017855],
            signed16DivisorHalfCast=True,quotientBits=15,remainderBits=24,initialRemainderMax=1312,
            shiftedRemainderMax=540827),
        asmPrimitiveBytes=primitive_bytes,localStackBytes=0,persistentDataBytes=0,
        asmCycleScope='Entry through RET; excludes caller rounding and all IRQ instructions/entry',
        normalCyclesFormula='212 + 3 * popcount(quotient)',negativeNumeratorCycles=9,saturationFastReturnCycles=19,
        cCycleScope='Original-expression O3 scalar wrapper including rounding, saturation, prologue/epilogue and RET; not a C decoder',
        cAndForcedGenericBinariesIdentical=True,physicalBoardTested=False,images=images)
    # No source contents, compiler host paths, media, environment or identities.
    serialized=json.dumps(receipt,indent=2)+'\n'
    assert not re.search(r'(?:[A-Za-z]:[\\/]|/home/|/Users/|/mnt/|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})',serialized)
    destination=ROOT/'reports/wb-ratio-unit.json'
    if args.check:assert json.loads(destination.read_text(encoding='utf-8'))==receipt,'Stale ratio unit receipt'
    else:destination.write_text(serialized,encoding='utf-8')
    print('PASS bounded ratio receipt: full bare/IRQ plus explicit C/generic IRQ controls')


if __name__=='__main__':main()
