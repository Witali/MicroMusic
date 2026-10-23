#!/usr/bin/env python3
"""Compare the retained NB baseline with completed final decoder/player runs."""
import argparse
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',nargs='+',type=Path,default=[ROOT/'reports/avr-optimized.json',ROOT/'reports/real-speech-avr.json'])
    parser.add_argument('--after',nargs='+',type=Path,default=[ROOT/'build/nb-final/avr-verification.json',ROOT/'build/nb-final-speech/avr-verification.json'])
    parser.add_argument('--players',type=Path,default=ROOT/'build/nb-final-player/player-all.json')
    parser.add_argument('--before-players',nargs='+',type=Path,default=[ROOT/'reports/player-all.json',ROOT/'reports/real-speech-player.json'])
    parser.add_argument('--compiler',default='AVR GCC 7.3.0 -O3 -flto -fwrapv -fno-strict-aliasing')
    parser.add_argument('--out',type=Path,default=ROOT/'build/nb-optimization-summary.json')
    args=parser.parse_args()
    baseline=[read(p) for p in args.before]
    final=[read(p) for p in args.after]
    players=read(args.players)
    before=max(r['maxCycles'] for r in baseline)
    after=max(r['maxCycles'] for r in final)
    assert sum(r['frames'] for r in final)==players['frames']==9100
    assert len(players['streams'])==31
    assert all(r['underruns']==0 for r in players['streams'])
    # PWM hashes must remain identical to the pre-optimization full player.
    old_players=[row for p in args.before_players for row in read(p)['streams']]
    old={r['input']['file']:r for r in old_players}
    for row in players['streams']:
        previous=old[row['input']['file']]
        assert row['input']['sha256']==previous['input']['sha256']
        assert row['pwmSha256']==previous['pwmSha256']
    report={'mcu':'ATmega328P','cpuHz':16000000,'pcmHz':8000,'pwmHz':62500,
            'compiler':args.compiler,
            'simulator':'avr8js 0.21.1','physicalBoardTested':False,
            'streams':31,'frames':players['frames'],'samples':players['samples'],
            'exactS16AgainstUpstream':True,'pwmHashesUnchanged':True,'underruns':0,
            'decoderFrameBudgetCycles':320000,'beforeMaxDecoderCycles':before,'afterMaxDecoderCycles':after,
            'decoderTimeReductionPercent':round((before-after)/before*100,3),
            'beforeMaxDecoderMs':before/16000,'afterMaxDecoderMs':after/16000,
            'beforeDecoderStaticSramBytes':baseline[0]['staticSramBytes'],
            'afterDecoderStaticSramBytes':final[0]['staticSramBytes'],
            'beforeDecoderFlashBytes':baseline[0]['flashBytes'],'afterDecoderFlashBytes':final[0]['flashBytes'],
            'beforePlayerStaticSramBytes':old_players[0]['staticSramBytes'],
            'afterPlayerStaticSramBytes':players['streams'][0]['staticSramBytes'],
            'beforePlayerFreeSramAtPeak':min(r['freeSramAtPeak'] for r in old_players),
            'afterPlayerFreeSramAtPeak':players['freeSramAtPeak'],
            'beforeMinQueuedSamples':min(r['minQueuedSamplesBeforeOutput'] for r in old_players if 'minQueuedSamplesBeforeOutput' in r),
            'beforeQueueMeasuredStreams':sum('minQueuedSamplesBeforeOutput' in r for r in old_players),
            'afterQueueMeasuredStreams':len(players['streams']),
            'afterMinQueuedSamples':min(r['minQueuedSamplesBeforeOutput'] for r in players['streams']),
            'maxBlockReadyGapCycles':max(r['maxBlockReadyGapCycles'] for r in players['streams']),
            'timerIntervalMinCycles':min(r['timerIntervalMinCycles'] for r in players['streams']),
            'timerIntervalMaxCycles':max(r['timerIntervalMaxCycles'] for r in players['streams']),
            'scope':'Decoder frame timings exclude ISR. All complete player streams include hardware timers and interrupt delivery. Corpus maxima are not an exhaustive timing proof.'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
