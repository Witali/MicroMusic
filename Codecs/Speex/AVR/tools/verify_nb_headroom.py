#!/usr/bin/env python3
"""Audit the complete-player 20% CPU admission test against the exact corpus.

The timer/ISR simulator must have verified each injected load instruction and
all PWM samples first. This audit checks coverage, hashes and per-frame loads.
It is a corpus-level ISA/peripheral verification, not a physical board test or
an exhaustive timing proof for every possible packet and application ISR.
"""
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=ROOT/'build/nb-headroom-20/player-all.json')
    parser.add_argument('--reserve-percent',type=int,default=20)
    parser.add_argument('--out',type=Path,default=ROOT/'build/nb-headroom-summary.json')
    args=parser.parse_args()
    if not 1<=args.reserve_percent<=90: parser.error('Reserve must be 1..90 percent')
    current=json.loads(args.report.read_text(encoding='utf-8'))
    baseline=json.loads((ROOT/'reports/nb-final-player.json').read_text(encoding='utf-8'))
    old={r['input']['file']:r for r in baseline['streams']}
    rows=current['streams']
    backends={r.get('backend','unrecorded') for r in rows}
    assert len(backends)==1, 'Do not mix arithmetic backends in one admission run'
    assert len(rows)==len(old)==31
    assert {r['input']['file'] for r in rows}==set(old)
    assert current['frames']==baseline['frames']==9100
    assert current['samples']==baseline['samples']==1456000
    assert current['includesInterrupts'] and not current['physicalBoardTested']
    required_cycles=3200*args.reserve_percent
    for row in rows:
        assert row.get('passed',True)
        previous=old[row['input']['file']]
        assert row['includesInterrupts'] and row['cpuHz']==16000000
        assert row['pcmHz']==8000 and row['pwmHz']==62500
        assert row['input']['sha256']==previous['input']['sha256']
        assert row['frames']==previous['frames']==row['measuredExtraLoadCount']
        assert row['samples']==previous['samples']
        assert row['pwmSha256']==previous['pwmSha256']
        assert row['extraCpuCyclesPerFrame']>=required_cycles
        assert row['input']['frameLoadCycles']==row['extraCpuCyclesPerFrame']
        assert row['measuredExtraLoadMinCycles']==row['extraCpuCyclesPerFrame']
        assert row['measuredExtraLoadMaxCycles']==row['extraCpuCyclesPerFrame']
        assert row['underruns']==0 and row['freeSramAtPeak']>0
        assert row['minQueuedSamplesBeforeOutput']>0
        assert row['timerIntervalMinCycles']>=1992 and row['timerIntervalMaxCycles']<=2008
    minimum_load=min(r['measuredExtraLoadMinCycles'] for r in rows)
    report={'goal':f'At least {args.reserve_percent}% CPU-time reserve while decoding Speex NB',
            'arithmeticBackend':next(iter(backends)),
            'mcu':'ATmega328P','cpuHz':16000000,'frameMs':20,'frameBudgetCycles':320000,
            'requiredReservePercent':args.reserve_percent,'verifiedExtraCpuCyclesPerFrame':minimum_load,
            'verifiedExtraCpuMsPerFrame':minimum_load/16000,
            'verifiedReserveAtLeastPercent':minimum_load/320000*100,
            'streams':len(rows),'frames':current['frames'],'samples':current['samples'],
            'measuredExtraLoadExecutions':sum(r['measuredExtraLoadCount'] for r in rows),
            'underruns':0,'pwmHashesUnchanged':True,'includesInterrupts':True,
            'freeSramAtPeak':min(r['freeSramAtPeak'] for r in rows),
            'minQueuedSamplesUnderLoad':min(r['minQueuedSamplesBeforeOutput'] for r in rows),
            'maxBlockReadyGapCyclesUnderLoad':max(r['maxBlockReadyGapCycles'] for r in rows),
            'physicalBoardTested':False,
            'method':f'Inject at least {required_cycles} independently counted foreground instruction cycles in every 320000-cycle audio frame. Timer/ISR execution consumes additional wall time and stays enabled during playback. Require exact PWM, zero underruns and intact SRAM for the same complete 31-stream corpus.',
            'scope':'Measured corpus on AVR8js 0.21.1 and AVR GCC 7.3.0; additional application I/O/ISRs and physical clock timing require their own validation.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
