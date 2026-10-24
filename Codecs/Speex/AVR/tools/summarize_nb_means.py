"""Compare matched AVR workloads using weighted per-stream mean cycles.

Means in the source reports are rounded to whole cycles; these aggregate
figures have less than one cycle/frame of rounding uncertainty. Maximum frame
costs remain separate, so mean gains never masquerade as worst-case gains.
"""
import argparse
import json
from pathlib import Path

def read_rows(paths):
    rows={}
    for path in paths:
        for row in json.loads(path.read_text())['streams']:
            assert row['stream'] not in rows,'Duplicate stream'
            rows[row['stream']]=row
    return rows

def stats(rows):
    frames=sum(r['frames'] for r in rows)
    before=sum(r['frames']*r['beforeMeanCycles'] for r in rows)
    after=sum(r['frames']*r['afterMeanCycles'] for r in rows)
    return {'streams':len(rows),'frames':frames,
            'beforeWeightedMeanCycles':round(before/frames,3),
            'afterWeightedMeanCycles':round(after/frames,3),
            'weightedMeanTimeReductionPercent':round((before-after)/before*100,4),
            'beforeMaxCycles':max(r['beforeMaxCycles'] for r in rows),
            'afterMaxCycles':max(r['afterMaxCycles'] for r in rows),
            'minimumStreamMeanReductionPercent':min(r['meanTimeReductionPercent'] for r in rows)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',nargs='+',type=Path,required=True)
    parser.add_argument('--after',nargs='+',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    before,after=read_rows(args.before),read_rows(args.after)
    assert set(before)==set(after),'Compare exactly the same named streams'
    rows=[]
    for name,new in after.items():
        old=before[name]
        assert old['frames']==new['frames']
        rows.append({'stream':name,'frames':new['frames'],
            'beforeMeanCycles':old['meanCycles'],'afterMeanCycles':new['meanCycles'],
            'beforeMaxCycles':old['maxCycles'],'afterMaxCycles':new['maxCycles'],
            'meanTimeReductionPercent':round((old['meanCycles']-new['meanCycles'])/old['meanCycles']*100,4)})
    report={'scope':'Matched decoder-only AVR runs; per-stream means rounded to cycles; ISR excluded.',
            'beforeReports':[str(p) for p in args.before],'afterReports':[str(p) for p in args.after],
            'allStreams':stats(rows),'streams':rows}
    human=[r for r in rows if r['stream'].startswith(('ru_','en_'))]
    if human:report['humanSpeech']=stats(human)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='streams'},indent=2))
