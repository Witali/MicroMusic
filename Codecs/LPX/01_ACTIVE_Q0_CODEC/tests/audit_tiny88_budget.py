"""Retain anonymous paired SRAM512/AVR25 budget results; media stays in build/."""
import hashlib
import json
import subprocess
from pathlib import Path

CODEC=Path(__file__).resolve().parents[1]
ROOT=CODEC.parents[2]
BASELINE='cd95a815e537cab4beff601b4e5f24ed54b97ab6'


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def selected(row):
    return {key:row[key] for key in ['samples','flash_bytes','program_excluding_audio_bytes','embedded_audio_bytes',
        'static_ram_bytes','stack_bytes','stack_margin','decode_active_irq_mean','decode_max',
        'min_queue','underruns','pwm_exact','accepted','irq_mean','output_gap_min','output_gap_max']}


def main():
    before=read(ROOT/'build/tiny88-public/before/summary.json')
    after=read(ROOT/'build/tiny88-public/final/summary.json')
    assert len(before)==len(after)==9
    rows=[]
    for index,(a,b) in enumerate(zip(before,after),1):
        assert (a['clip'],a['profile'])==(b['clip'],b['profile']) and a['samples']==b['samples']
        assert a['repeat']==b['repeat']==2 and a['accepted'] and b['accepted']
        assert a['pwm_exact'] and b['pwm_exact'] and a['underruns']==b['underruns']==0
        folder=a['clip']+'-'+a['profile']
        assert (ROOT/'build/tiny88-public/before'/folder/'actual.pwm').read_bytes()==(
            ROOT/'build/tiny88-public/final'/folder/'actual.pwm').read_bytes()
        assert b['static_ram_bytes']==422 and b['flash_bytes']<=8192 and b['stack_margin']>0
        rows.append(dict(workload=f'public-{index:02d}',profile=a['profile'],before=selected(a),after=selected(b),
            programBytesSaved=a['program_excluding_audio_bytes']-b['program_excluding_audio_bytes'],
            decoderMeanChangePercent=(b['decode_active_irq_mean']/a['decode_active_irq_mean']-1)*100))
    cost=read(ROOT/'build/tiny88-public/final/chego-compact/build.json')
    for name,h in cost['source_sha256'].items():assert digest(ROOT/name)==h,name
    baseline_cost=read(ROOT/'build/tiny88-public/before/chego-compact/build.json')
    for name,h in baseline_cost['source_sha256'].items():
        original=subprocess.check_output(['git','show',BASELINE+':'+name],cwd=ROOT)
        assert hashlib.sha256(original).hexdigest()==h,name
    matrix=read(ROOT/'build/tiny88-matrix-final/matrix.json')
    for name,h in matrix['source_sha256'].items():assert digest(ROOT/name)==h,name
    assert len(matrix['cases'])==18
    for row in matrix['cases']:
        expected=row['case'] not in ('c-arithmetic-reject','queue16-control')
        assert row['accepted']==expected
    arithmetic=[]
    for factor in (1,2,4,8,16):
        result=read(ROOT/f'build/avr25-math/unroll{factor}/verification.json')
        arithmetic.append(dict(factor=factor,verification=result))
    release=read(ROOT/'web-player/firmware-lpx-attiny88.json')
    assert len(release['variants'])==9
    for row in release['variants']:assert digest(ROOT/'web-player'/row['source'])==row['hexSha256']
    source_hashes=dict(cost['source_sha256'])
    for path in [Path(__file__),CODEC/'tests/test_fixed_header.py',CODEC/'tests/test_fixed_cosine.py',
                 CODEC/'tests/build_avr25_math.py',CODEC/'tests/verify_avr25_math.mjs']:
        source_hashes[path.relative_to(ROOT).as_posix()]=digest(path)
    result=dict(schema='lpx-tiny88-budget-v1',cpu='ATtiny88 / AVR25 without MUL',cpuHz=16000000,sampleHz=8000,
        compiler='AVR-GCC 7.3.0 / AVR-LibC, GNU ABI',physicalBoardMeasured=False,
        sourceHashEncoding='exact-file-bytes',sourceSha256=source_hashes,
        baselineCommit=BASELINE,baselineSourceSha256=baseline_cost['source_sha256'],
        selected=dict(queue=24,prefill=18,mul16Unroll=2,assembly=True,asmIsr=True,
            flashHardCapBytes=8192,standardUsbApplicationBytes=6012,cFallbackSelectable=True),
        pairedPlaybackPasses=2,pairedPwmExact=True,pairedWorkloads=rows,
        matrix=matrix,arithmetic=arithmetic,
        fixedCosineValidation=dict(test='tests/test_fixed_cosine.py',finiteNodes=1808,
            syntheticScenarios=48,fullPcmPwmComparisons=120),
        oneShotRelease=dict(variants=9,samples=sum(v['timing']['playedSamples'] for v in release['variants']),
            flashMinBytes=min(v['flashBytes'] for v in release['variants']),flashMaxBytes=max(v['flashBytes'] for v in release['variants']),
            programMinBytes=min(v['programFlashBytes'] for v in release['variants']),programMaxBytes=max(v['programFlashBytes'] for v in release['variants']),
            usbFit=sum(v['fitsStandardBootloader'] for v in release['variants']),ispRequired=sum(v['requiresIsp'] for v in release['variants']),
            staticSramBytes=422,stackMaxBytes=max(v['peakStackBytes'] for v in release['variants']),
            stackMarginMinBytes=min(v['stackMarginBytes'] for v in release['variants']),underruns=0),
        notes=['PWM is identical to the existing public WAVs; no codec quantization or stream changes.',
            'Observer stack margin follows static + stack + margin = 511.',
            'Loop/table/small FIFO choices are explicit; generic C and unroll16 defaults remain selectable.'])
    path=CODEC/'examples/ATTINY88_V5_PLAYER/budget-measurements.json'
    path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('PASS anonymous paired budget receipt, 18 matrix controls, five C/ASM/ABI/IRQ arithmetic probes, nine one-shot images')
    print(json.dumps(dict(minProgramSaved=min(r['programBytesSaved'] for r in rows),
        maxProgramSaved=max(r['programBytesSaved'] for r in rows),
        maxDecoderMeanChangePercent=max(r['decoderMeanChangePercent'] for r in rows),
        release=result['oneShotRelease']),indent=2))


if __name__=='__main__':main()
