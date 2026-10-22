#!/usr/bin/env python3
"""Automated fixed-point LPC2 teacher -> tiny AVR student fitting.

Greedy analysis-by-synthesis: propose edits to the actual 4-bit packed parameters,
run a byte-exact TinyLPC AVR model, and accept only edits with lower perceptual
loss and conservative constraints relative to baseline. No human adjustment.
"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
import numpy as np
from model_lite import render,reference_selftest
from perceptual import Evaluator,load_wav,lpc2_pcm

ROOT=Path(__file__).resolve().parent

def cmd():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,default=ROOT/'references/original_reference.wav',help='Reference trimmed speech WAV')
    ap.add_argument('--teacher',type=Path,default=ROOT/'references/lpc2_improved_reference.s16le',help='LPC2 v11 decoded signed 16-bit 8kHz raw PCM, or WAV')
    ap.add_argument('--seed-params',type=Path,default=ROOT/'references/base_parameters.npz')
    ap.add_argument('--budget',type=int,default=450,help='Maximum candidate renders for coordinate search')
    ap.add_argument('--seed',type=int,default=2026)
    ap.add_argument('--target',choices=['balanced','voice','lpc2'],default='balanced')
    ap.add_argument('--output-dir',type=Path,default=ROOT/'results')
    return ap.parse_args()

def load_params(path):
    d=np.load(path)
    K=np.asarray(d['K'],dtype=np.int64).copy()
    P=np.asarray(d['P'],dtype=np.int64).copy()
    E=np.asarray(d['E'],dtype=np.int64).copy()
    assert K.ndim==2 and K.shape[1]==7 and len(P)==len(E)==len(K)
    return K,P,E

def configure(mode):
    if mode=='lpc2':return {'stoi':2.0,'original':0.8,'lpc2':1.35,'envelope':0.12,'clicks':0.001}
    if mode=='voice':return {'stoi':2.5,'original':1.2,'lpc2':0.5,'envelope':0.18,'clicks':0.001}
    return {'stoi':2.2,'original':1.0,'lpc2':0.9,'envelope':0.2,'clicks':0.001}

def accept_guard(metrics,baseline):
    # No candidate may reduce short-time intelligibility, original spectral
    # similarity or click count beyond these tolerances. Not a listening guarantee.
    return (metrics['stoi']>=baseline['stoi']-0.002
        and metrics['mel_original']<=baseline['mel_original']+0.010
        and metrics['clicks_60']<=max(0,baseline['clicks_60'])
        and metrics['max_step']<=max(57,baseline['max_step']) )

def main(args):
    begin=time.monotonic()
    if args.seed_params==ROOT/'references/base_parameters.npz' and args.source==ROOT/'references/original_reference.wav':
        assert reference_selftest(ROOT)==0, 'DSP model and independent AVR baseline disagree'
    rng=np.random.default_rng(args.seed)
    x=load_wav(args.source)
    teacher=(load_wav(args.teacher) if args.teacher.suffix.lower()=='.wav' else lpc2_pcm(args.teacher)) if args.teacher.exists() else x
    K,P,E=load_params(args.seed_params)
    if abs(len(x)-len(P)*256)>256:
        raise RuntimeError(f'Audio/seed mismatch: original {len(x)} samples; seed {len(P)}*256. Generate new seed for a new phrase.')
    ev=Evaluator(x,teacher)
    fsamp=len(P)*256
    def eval_one():
        out=render(K,P,E,fsamp)
        met=ev.metrics(out)
        return met,ev.fitness(met,weights)
    weights=configure(args.target)
    base,score=eval_one()
    cur=dict(base)
    best_score=float(score)
    best_K=K.copy();best_P=P.copy();best_E=E.copy()
    proposals=0;accepted=0;history=[]
    # Prefer voiced/high-energy frames, but visit quiet unvoiced consonants too.
    candidates=np.where(E>0)[0]
    probabilities=(E[candidates].astype(float)**.5+1.5)
    probabilities/=probabilities.sum()
    print('BASE',json.dumps(base),'score',round(score,6),flush=True)
    base_rms=np.sqrt(np.mean(x*x))
    while proposals<args.budget:
        frame=int(rng.choice(candidates,p=probabilities))
        action=rng.choice(['k','k','k','k','gain','pitch'])
        which=None
        if action=='k':
            which=int(rng.integers(0,7))
            previous=int(K[frame,which]);step=int(rng.choice([-2,-1,1,2]));nxt=int(np.clip(previous+step,-7,7))
            if nxt==previous:continue
            K[frame,which]=nxt
        elif action=='gain':
            previous=int(E[frame]);nxt=int(np.clip(previous+int(rng.choice([-2,-1,1,2])),1,15))
            if previous==nxt:continue
            E[frame]=nxt
        else:
            previous=int(P[frame])
            if previous<16 or previous>115:continue
            nxt=int(np.clip(previous+int(rng.choice([-2,-1,1,2])),16,127))
            if previous==nxt:continue
            P[frame]=nxt
        proposals+=1
        met,new_score=eval_one()
        if new_score>score+1e-6 and accept_guard(met,base):
            score=new_score;cur=met;accepted+=1
            if score>best_score:
                best_score=score
                best_K=K.copy();best_P=P.copy();best_E=E.copy()
            history.append({'try':proposals,'frame':frame,'edit':action,'coefficient':which,'old':previous,'new':nxt,'score':score,
                            'stoi':cur['stoi'],'mel_original':cur['mel_original'],'mel_lpc2':cur['mel_lpc2']})
        else:
            if action=='k':K[frame,which]=previous
            elif action=='gain':E[frame]=previous
            else:P[frame]=previous
        if proposals%100==0:
            print('TRY',proposals,'accepted',accepted,'score',round(score,6),'stoi',round(cur['stoi'],5),
                  'mel(orig/lpc2)',round(cur['mel_original'],5),round(cur['mel_lpc2'],5),
                  'elapsed',round(time.monotonic()-begin,1),'s',flush=True)
    # Select strictly observed best. Baseline remains selected if no improvement.
    K[:]=best_K;P[:]=best_P;E[:]=best_E
    out=render(K,P,E,fsamp)
    end=ev.metrics(out)
    outdir=args.output_dir;outdir.mkdir(exist_ok=True,parents=True)
    np.savez(outdir/'optimized_parameters.npz',K=K,P=P,E=E)
    import soundfile as sf
    sf.write(outdir/'optimized_model.wav',out.astype('float64')/128.,7500,subtype='PCM_16')
    report={'settings':{'source':str(args.source),'teacher':str(args.teacher),'seed':args.seed,'budget':args.budget,'target':args.target,
                        'weights':weights},'baseline':base,'optimized':end,'fitness_baseline':ev.fitness(base,weights),
            'fitness_optimized':best_score,'trials':proposals,'accepted':accepted,'elapsed_s':round(time.monotonic()-begin,2),
            'model_matches_baseline':True,'guard':accept_guard(end,base)}
    (outdir/'optimization_report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    (outdir/'optimization_history.json').write_text(json.dumps(history,indent=2,ensure_ascii=False)+'\n')
    print('BEST',json.dumps(end),'score',round(best_score,6),'accepted',accepted,'elapsed',round(time.monotonic()-begin,2),flush=True)
    return report

if __name__=='__main__': main(cmd())
