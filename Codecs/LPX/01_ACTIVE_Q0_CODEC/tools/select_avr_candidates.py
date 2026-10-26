"""Explicit full-ELF AVR selection among already encoded LPX candidates.

Keeps the target baseline SSE/STOI floors and byte cap. A bounded heuristic
shortlist is measured; its size/quality/time frontier is reported. This is not
a claim of a global optimum over unmeasured candidates. Default encoders and
the historical benchmark selection remain unchanged.
"""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import soundfile as sf
from avr_timing_gate import AvrTimingGate
from batch_decoder import BatchSession
from output_paths import protect_outputs
from wav_to_lpx4 import quality

def sha(blob):return hashlib.sha256(blob).hexdigest()
def stoi_cost(point):
    value=point[2]['quality']['stoi']
    return -value if value is not None else 0.

def frontier(points,objective):
    """Minimize every objective; retain ties for deterministic content tie-breaks."""
    rows=[(p,objective(p)) for p in points]
    return [p for p,v in rows if not any(all(a<=b for a,b in zip(w,v)) and
        any(a<b for a,b in zip(w,v)) for _,w in rows)]

def select(candidates,baseline,max_bytes,gate,max_measurements=6):
    if not 1<=max_measurements<=64:raise ValueError('Expected 1..64 complete ELF measurements')
    floor=baseline[2]['quality']['stoi'];limit=baseline[2]['full_sse']
    eligible={sha(p[0]):p for p in [*candidates,baseline] if len(p[0])<=max_bytes and
        p[2]['full_sse']<=limit and (floor is None or
        (p[2]['quality']['stoi'] is not None and p[2]['quality']['stoi']>=floor-1e-12))}
    base_sha=sha(baseline[0])
    if base_sha not in eligible:raise ValueError('Baseline exceeds file cap')
    # Preserve the rollback even when a candidate dominates its quality/size.
    shortlist=[baseline];seen={base_sha}
    # A size/quality-dominated stream may decode faster. Do not discard it
    # before measuring CPU time; balance ranks across the entire eligible pool.
    pool=list(eligible.values())
    orders=[sorted(pool,key=key) for key in (
        lambda p:(p[2]['full_sse'],len(p[0]),sha(p[0])),
        lambda p:(len(p[0]),p[2]['full_sse'],sha(p[0])),
        lambda p:(stoi_cost(p),p[2]['full_sse'],len(p[0]),sha(p[0])))]
    for index in range(len(pool)):
        for order in orders:
            p=order[index];key=sha(p[0])
            if key not in seen and len(shortlist)<max_measurements:
                shortlist.append(p);seen.add(key)
    measured=[];accepted=[]
    for p in shortlist:
        timing=gate(p[0]);key=sha(p[0])
        row={'stream_sha256':key,'file_bytes':len(p[0]),'full_sse':p[2]['full_sse'],
             'stoi':p[2]['quality']['stoi'],**timing}
        measured.append(row)
        if timing['accepted']:accepted.append((p,row))
    if not any(sha(p[0])==base_sha for p,_ in accepted):
        raise ValueError('Baseline failed the complete-ELF timing gate')
    def objective(pair):
        p,r=pair
        return (p[2]['full_sse'],stoi_cost(p),len(p[0]),r['flash_bytes'],
                r['mean_decode_wall_cycles'],r['decode_wall_cycles_max_160'])
    boundary=frontier(accepted,objective)
    selected=min(boundary,key=lambda pair:(pair[0][2]['full_sse'],stoi_cost(pair[0]),
        pair[1]['flash_bytes'],pair[1]['mean_decode_wall_cycles'],
        pair[1]['decode_wall_cycles_max_160'],len(pair[0][0]),sha(pair[0][0])))
    report={'eligible_unique':len(eligible),'measurement_limit':max_measurements,
        'measured':measured,'frontier_sha256':[sha(p[0]) for p,_ in boundary],
        'baseline_sha256':base_sha,'selected_sha256':sha(selected[0][0]),
        'cap_file_bytes':max_bytes,'quality_floor':{'full_sse':limit,'stoi':floor},
        'scope':'Bounded shortlist only; unmeasured streams may have a better time/size tradeoff.'}
    return selected[0],report

def run(reference,baseline,candidates,output,max_bytes,avr_bin,runner,lib=None,wsl=None,
        kind='speech',max_measurements=6,queue=512,prefill=384,unroll=9,irq_load=0,v3_features=24):
    reference,baseline,output=map(Path,(reference,baseline,output))
    candidates=list(map(Path,candidates));report_path=output.with_suffix('.json')
    protect_outputs([reference,baseline,*candidates],[output,report_path])
    ref,rate=sf.read(reference,dtype='int16')
    if rate!=8000 or ref.ndim!=1 or not 1<=len(ref)<=64000:
        raise ValueError('Expected mono 8kHz PCM reference, 1..64000 samples')
    records={};points=[]
    with BatchSession('batch',v3_features=v3_features) as decoder:
        for path in [baseline,*candidates]:
            blob=path.read_bytes();key=sha(blob)
            if key in records:continue
            pcm=decoder.decode_one_s16(blob,len(ref))
            if pcm is None:raise ValueError('Invalid stream or reference length: '+str(path))
            error=pcm.astype(np.int64)-ref.astype(np.int64)
            point=(blob,pcm,{'full_sse':int(np.dot(error,error)),
                'quality':quality(ref,pcm,kind),'path':str(path)})
            records[key]=point;points.append(point)
    base=records[sha(baseline.read_bytes())]
    gate=AvrTimingGate(base[0],output.parent/(output.stem+'-avr'),avr_bin,runner,lib,wsl,
        v3_features=v3_features,queue=queue,prefill=prefill,dot_unroll=unroll,irq_load=irq_load)
    selected,report=select(points,base,max_bytes,gate,max_measurements)
    report.update(reference_sha256=sha(ref.astype('<i2').tobytes()),samples=len(ref),
        selected_pcm16_sha256=sha(selected[1].astype('<i2').tobytes()),physical_hardware_measured=False,
        profile=gate.settings,inputs=[{'path':p[2]['path'],'stream_sha256':sha(p[0])} for p in points])
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(selected[0])
    report_path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('reference',type=Path);ap.add_argument('baseline',type=Path)
    ap.add_argument('output',type=Path);ap.add_argument('candidates',type=Path,nargs='*')
    ap.add_argument('--cap-file-bytes',type=int,required=True)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--sim-runner',type=Path,required=True)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    ap.add_argument('--kind',choices=('speech','music','synthetic'),default='speech')
    ap.add_argument('--max-measurements',type=int,default=6)
    ap.add_argument('--queue',type=int,default=512);ap.add_argument('--prefill',type=int,default=384)
    ap.add_argument('--dot-unroll',type=int,choices=(1,3,9),default=9)
    ap.add_argument('--irq-load',type=int,default=0)
    ap.add_argument('--v3-features',type=int,default=24)
    a=ap.parse_args();r=run(a.reference,a.baseline,a.candidates,a.output,a.cap_file_bytes,a.avr_bin,
        a.sim_runner,a.sim_lib_dir,a.wsl,a.kind,a.max_measurements,a.queue,a.prefill,a.dot_unroll,a.irq_load,a.v3_features)
    print(json.dumps({k:r[k] for k in ('eligible_unique','selected_sha256','frontier_sha256')},indent=2))
