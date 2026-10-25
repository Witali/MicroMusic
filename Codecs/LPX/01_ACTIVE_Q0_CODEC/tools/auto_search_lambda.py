#!/usr/bin/env python3
"""MicroMusic LPX4 automatic offline rate/distortion coefficient search.

Search the *actual final L4HY byte length* while imposing independently
verified quality gates on output of the very same integer C++ decoder used
by ATmega328P. All search effort is on the desktop.

Input: existing legacy LPC2/LPX3 analysis+LSF and coeff trace, 8-kHz WAV.
This is a frontend for the recovered VBR encoder; it does NOT analyze a
previously unseen WAV into LPC/LSF automatically (that is a separate stage).
"""
from __future__ import annotations
import argparse,sys,json,hashlib,subprocess,tempfile,wave,math
from pathlib import Path
from dataclasses import asdict,dataclass
from typing import Optional
import numpy as np
import soundfile as sf
from pystoi import stoi

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT/'encoder_vbr'/'tools'))
from encode_vbr_fixedexact import make as make_l3av
from lpx4 import encode as make_lpx4
from l3av_parse import unpack

# Deterministic finite search. Dense interval around the historically useful
# lambda range, plus broad coverage to avoid tuning only to existing samples.
DEFAULT_LAMBDAS=tuple(sorted(set(
    [0.0,.00005,.00010,.00020,.00035,.00050,.00075,.0010,.0015,.0025,.0040,.0080,.0120] +
    [round(.00060+i*.00005,8) for i in range(39)]
)))

@dataclass
class Result:
    label:str
    size_bytes:int
    pcm_snr_db:float
    stoi:float
    pcm_sha256:str
    accepted:bool=False
    rejection:str=""
    lambda_value:Optional[float]=None
    effective_bps:Optional[float]=None
    exact_lpx4:bool=True
    decode_cost_proxy:Optional[dict]=None

def read_truth(path):
    with wave.open(str(path),'rb') as w:
        if (w.getnchannels(),w.getframerate(),w.getsampwidth())!=(1,8000,2):
            raise ValueError('expected mono 8000Hz PCM16 reference wav')
        x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64)/32768.0
    if len(x)<256:raise ValueError('audio too short to measure STOI')
    return x

def evaluate_raw(name,blob,raw,wav,work,metrics_decoder=None):
    """Original, unchanged STOI/SNR arithmetic; one candidate's decoded PCM."""
    v=np.frombuffer(raw,dtype=np.uint8).astype(np.float64)/128.0-1
    if len(v)!=len(wav):raise ValueError(f'length mismatch {len(v)} vs {len(wav)}')
    err=wav-v
    snr=10*np.log10(max(float(np.mean(wav**2)),1e-30)/max(float(np.mean(err**2)),1e-30))
    cost=None
    if metrics_decoder is not None:
        p=work/'candidate.l4hy';p.write_bytes(blob)
        metric_run=subprocess.run([str(metrics_decoder.resolve()),str(p)],
                                  text=True,capture_output=True,check=True)
        cost=json.loads(metric_run.stdout)
        if cost['samples']!=len(v):raise AssertionError('metrics count mismatch')
    return Result(name,len(blob),float(snr),float(stoi(wav,v,8000,extended=False)),
                  hashlib.sha256(raw).hexdigest(),effective_bps=8*len(blob)*8000/len(raw),
                  decode_cost_proxy=cost)


def evaluate(name,blob,exe,wav,work,metrics_decoder=None,batch_decoder=None):
    if batch_decoder is not None:
        decoded=batch_decoder.decode_one(blob,len(wav))
        if decoded is None:raise ValueError(f'C++ rejected {name} (native batch decoder)')
        raw=decoded.tobytes()
    else:
        p=work/'candidate.l4hy';p.write_bytes(blob)
        pcm=work/'candidate.pcm'
        cmd=[str(exe.resolve()),str(p),str(pcm)]
        r=subprocess.run(cmd,text=True,capture_output=True,check=False)
        if r.returncode:raise ValueError(f'C++ rejected {name}: {r.stderr[:350]}')
        raw=pcm.read_bytes()
    return evaluate_raw(name,blob,raw,wav,work,metrics_decoder)


def evaluate_many(entries,exe,wav,work,metrics_decoder=None,batch_decoder=None,batch_size=16):
    """Decode LPC candidates in groups, then preserve scalar STOI ordering.

    entries: [(lambda, encoded_byte_stream), ...]  Handles failures separately
    from the encoder stage. Exact output and selection policy remain unchanged.
    """
    if batch_decoder is None:
        results=[]
        for v,blob in entries:
            try:results.append(evaluate('lambda='+str(v),blob,exe,wav,work,metrics_decoder))
            except (ValueError,AssertionError,RuntimeError) as exc:results.append(exc)
        return results
    if batch_size<1 or batch_size>512:
        raise ValueError('batch_size must be between 1 and 512')
    output=[]
    for pos in range(0,len(entries),batch_size):
        group=entries[pos:pos+batch_size]
        waves=batch_decoder.decode_many([blob for _,blob in group],len(wav))
        for (value,blob),pcm in zip(group,waves):
            if pcm is None:
                output.append(ValueError('C++ rejected lambda='+str(value)))
            else:
                try:
                    output.append(evaluate_raw('lambda='+str(value),blob,pcm.tobytes(),
                                               wav,work,metrics_decoder))
                except (ValueError,AssertionError,RuntimeError) as exc:
                    output.append(exc)
    return output

def eligible(test,reference,min_stoi=None,max_stoi_drop=.00025,max_snr_drop=.05,max_bytes=None,min_pcm_snr=25.,max_cost_growth=.05):
    if max_bytes is not None and test.size_bytes>max_bytes:
        return False,'larger than size cap'
    if test.pcm_snr_db+1e-9<min_pcm_snr:
        return False,'below absolute PCM-SNR floor'
    if min_stoi is not None and test.stoi+1e-9<min_stoi:
        return False,'below minimum STOI'
    if reference.decode_cost_proxy is not None and test.decode_cost_proxy is not None:
        br=reference.decode_cost_proxy;tr=test.decode_cost_proxy
        for prop in ('bit_calls','max_bit_calls_160'):
            if tr[prop]>br[prop]*(1+max_cost_growth)+1:
                return False,'read-bit operation proxy grows: '+prop
        if tr['max_bit_calls_sample']>br['max_bit_calls_sample']+8:
            return False,'read-bit peak single-sample proxy grows'
        if tr['lsf_converts']>br['lsf_converts']:
            return False,'additional LPC coefficient conversions'
    if test.stoi+1e-9<reference.stoi-max_stoi_drop:
        return False,'STOI regression'
    if test.pcm_snr_db+1e-9<reference.pcm_snr_db-max_snr_drop:
        return False,'SNR regression'
    return True,''

def run(opts):
    source=opts.source.resolve();truth=read_truth(opts.wav);exe=opts.decoder.resolve()
    metric_exe=opts.metrics_decoder.resolve() if opts.metrics_decoder else None
    if metric_exe is not None and not metric_exe.is_file():raise FileNotFoundError(metric_exe)
    analysis=opts.lsf_json.resolve();trace=opts.coeff_trace.resolve();legacy=opts.legacy_lpx3.resolve()
    if opts.baseline is None and opts.min_stoi is None:
        raise ValueError('Supply --baseline or an explicit --min-stoi quality floor')
    for path in (source,analysis,trace,legacy,exe):
        if not path.is_file():raise FileNotFoundError(path)
    if opts.baseline and not opts.baseline.is_file():raise FileNotFoundError(opts.baseline)
    lambdas=list(DEFAULT_LAMBDAS) if opts.lambda_grid.strip().lower()=='auto' else [float(x) for x in opts.lambda_grid.split(',')]
    if any(not np.isfinite(v) or v<0 for v in lambdas):raise ValueError('lambda must be nonnegative and finite')
    output=opts.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    from batch_decoder import BatchSession
    with BatchSession(getattr(opts,'decode_backend','auto')) as batch, tempfile.TemporaryDirectory(prefix='lpx4_auto_') as tmp:
        work=Path(tmp);options=[]
        if opts.baseline:
            baseblob=opts.baseline.read_bytes()
            baseline=evaluate('previous accepted LPX4',baseblob,exe,truth,work,metric_exe,batch_decoder=batch)
            baseline.accepted=True
            options.append((baseline,baseblob))
            best=baseline;bestblob=baseblob
            max_bytes=baseline.size_bytes if opts.no_growth else None
        else:
            # Bootstrap with the first valid auto-encoded candidate; this first
            # result is not assumed to be a quality-independent reference.
            baseline=None;best=None;bestblob=None;max_bytes=None
        x,sr=sf.read(str(opts.wav),always_2d=False)
        if sr!=8000 or np.ndim(x)!=1:raise ValueError('expected mono 8kHz WAV')
        is_fast=opts.encoder_backend=='fast'
        if is_fast:
            from fast_vbr import Prepared
            prepared=Prepared(x,analysis,trace,legacy)
        else:
            prepared=None
        # Generate first, score later: parameter search is offline and independent
        # of prior candidates. This removes repeated process launches and batches
        # the costly C++ LPC synthesis. Error reports retain their lambda order.
        generated=[]
        for value in lambdas:
            l3=work/'candidate.l3av'
            try:
                make_l3av(x,analysis,trace,legacy,l3,value,
                          fast=is_fast,context=prepared)
                blob,meta,chunks,recovered=make_lpx4(unpack(l3.read_bytes()),float('inf'),fast=is_fast)
                generated.append((value,blob,None))
            except (ValueError,AssertionError,RuntimeError) as exc:
                generated.append((value,None,str(exc)))
        valid=[(v,blob) for v,blob,error in generated if error is None]
        measured_iter=iter(evaluate_many(valid,exe,truth,work,metric_exe,
                              batch_decoder=batch,batch_size=getattr(opts,'batch_size',16)))
        for value,blob,error in generated:
            if error is not None:
                options.append((Result(f'lambda={value}',0,0,0,'',rejection=error),b''))
                continue
            try:
                result=next(measured_iter)
                if isinstance(result,Exception):raise result
                result.lambda_value=value;result.exact_lpx4=True
                reference=baseline or result
                result.accepted,result.rejection=eligible(result,reference,opts.min_stoi,
                    opts.max_stoi_drop,opts.max_snr_drop,max_bytes,opts.min_pcm_snr,opts.max_cost_growth)
                if result.accepted and (best is None or (result.size_bytes,-result.pcm_snr_db,-result.stoi)<
                                      (best.size_bytes,-best.pcm_snr_db,-best.stoi)):
                    best=result;bestblob=blob
                options.append((result,blob))
            except (ValueError,AssertionError,RuntimeError) as exc:
                options.append((Result(f'lambda={value}',0,0,0,'',rejection=str(exc)),b''))
        if best is None:raise RuntimeError('No candidate satisfies quality thresholds; supply a proven --baseline or relax thresholds.')
        # Second automatic stage: optimize the *existing fixed-size Q14 fields*.
        # It never increases bitstream size or AVR computational work.
        optimizer_reports={}
        from tune_header_fixedrate import run as tune_header
        from refine_fixedrate import refine as refine_pulses
        if not opts.skip_pulse_search and opts.pulse_evals>0:
            pulse_input=work/'pulse_in.l4hy';pulse_out=work/'pulse_out.l4hy'
            pulse_input.write_bytes(bestblob)
            pstats=refine_pulses(pulse_input,opts.wav,exe,pulse_out,
                                 passes=1,max_eval=opts.pulse_evals,batch_decoder=batch)
            optimizer_reports['pulses']={k:v for k,v in pstats.items() if k!='changes'}
            pblob=pulse_out.read_bytes()
            ptest=evaluate('auto tuned CELP pulses',pblob,exe,truth,work,metric_exe,batch_decoder=batch)
            ok,why=eligible(ptest,baseline or best,opts.min_stoi,opts.max_stoi_drop,
                            opts.max_snr_drop,max_bytes,opts.min_pcm_snr)
            if ok and len(pblob)<=len(bestblob) and ptest.pcm_snr_db>=best.pcm_snr_db-1e-10:
                ptest.lambda_value=best.lambda_value;ptest.accepted=True;best=ptest;bestblob=pblob
            else:optimizer_reports['pulses']['rejected']=why or 'no PCM improvement'
        if not opts.skip_header_tuning:
            header_input=work/'header_in.l4hy';header_out=work/'header_out.l4hy';header_report=work/'header.json'
            header_input.write_bytes(bestblob)
            hstats=tune_header(header_input,opts.wav,exe,header_out,header_report,max_trials=opts.header_trials,batch_decoder=batch)
            optimizer_reports['header']={k:v for k,v in hstats.items() if k!='accepted_changes'}
            hblob=header_out.read_bytes()
            htest=evaluate('auto tuned preQ14 / brightQ14',hblob,exe,truth,work,metric_exe,batch_decoder=batch)
            ok,why=eligible(htest,baseline or best,opts.min_stoi,opts.max_stoi_drop,
                            opts.max_snr_drop,max_bytes,opts.min_pcm_snr)
            if ok and len(hblob)<=len(bestblob) and htest.pcm_snr_db>=best.pcm_snr_db-1e-10:
                htest.lambda_value=best.lambda_value;htest.accepted=True;best=htest;bestblob=hblob
            else:optimizer_reports['header']['rejected']=why or 'no improvement'
        output.write_bytes(bestblob)
        check=evaluate('final recheck',output.read_bytes(),exe,truth,work,metric_exe,batch_decoder=batch)
        assert check.pcm_sha256==best.pcm_sha256 and check.size_bytes==best.size_bytes
        info={'quality_policy':{'max_stoi_drop':opts.max_stoi_drop,'max_snr_drop_db':opts.max_snr_drop,
                                'min_stoi':opts.min_stoi,'min_pcm_snr_db':opts.min_pcm_snr,'no_growth':opts.no_growth,
                                'max_read_bit_cost_proxy_growth':opts.max_cost_growth},
              'source_l3av':str(source),'source_wav':str(opts.wav),
              'encoder_backend':opts.encoder_backend,
              'decode_backend':('batch' if batch is not None else 'reference'),
              'native_batch_calls':(batch.calls if batch is not None else 0),
              'native_batch_streams':(batch.streams if batch is not None else 0),
              'batch_size':getattr(opts,'batch_size',16),
              'baseline':asdict(baseline) if baseline else None,
              'selected':asdict(best),'candidates':[asdict(z) for z,_ in options],
              'decoder_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
              'selected_file_sha256':hashlib.sha256(bestblob).hexdigest(),'post_tuning':optimizer_reports,
              'codec_notes':'Only quantizer lambda is searched; per-80-sample bit width/step and per-40-sample Rice k/mode/lag/gain are already optimized offline by the existing encoder.',
              'limitations':'This test uses reference 8 kHz WAV and a host C++ build; hardware AVR cycles are NOT measured. Avoid training and evaluating exclusively on same recordings.',
              'reference_prepared_8k_samples':int(len(truth))}
        if opts.report:
            opts.report.parent.mkdir(parents=True,exist_ok=True)
            opts.report.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'selected':info['selected'],'baseline':info['baseline'],
                          'candidate_count':len(options)},ensure_ascii=False,indent=2))
        return info

def cli():
    ap=argparse.ArgumentParser(description='Automatically choose LPX3 VBR lambda by final LPX4 bytes + exact decoded quality')
    ap.add_argument('--source',type=Path,required=True,help='L3AV v1 for matching legacy LPC2 structure')
    ap.add_argument('--wav',type=Path,required=True,help='matching PCM16/8kHz mono WAV')
    ap.add_argument('--lsf-json',type=Path,required=True)
    ap.add_argument('--coeff-trace',type=Path,required=True)
    ap.add_argument('--legacy-lpx3',type=Path,required=True)
    ap.add_argument('--decoder',type=Path,required=True,help='compiled C++ LPX4 host decoder')
    ap.add_argument('--baseline',type=Path,help='quality-accepted L4HY v2 for no-regression')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--report',type=Path)
    ap.add_argument('--lambda-grid',default='auto',help='auto = deterministic coarse+dense offline grid; or comma separated custom list')
    ap.add_argument('--encoder-backend',choices=('fast','reference'),default='fast',
                    help='fast uses cached analysis and Numba, reference is the original Python search')
    ap.add_argument('--decode-backend',choices=('auto','batch','reference'),default='auto',
                    help='batch loads one C++ shared library for PCM candidates; reference launches process per candidate')
    ap.add_argument('--batch-size',type=int,default=16,help='L4HY candidates per native LPC batch (1..512)')
    ap.add_argument('--min-stoi',type=float)
    ap.add_argument('--max-stoi-drop',type=float,default=.00025)
    ap.add_argument('--max-snr-drop',type=float,default=.05)
    ap.add_argument('--min-pcm-snr',type=float,default=25.0)
    ap.add_argument('--skip-header-tuning',action='store_true')
    ap.add_argument('--skip-pulse-search',action='store_true')
    ap.add_argument('--pulse-evals',type=int,default=100)
    ap.add_argument('--header-trials',type=int,default=256)
    ap.add_argument('--metrics-decoder',type=Path,help='optional independently instrumented C++ decoder; read-bit cost is NOT AVR cycles')
    ap.add_argument('--max-cost-growth',type=float,default=.05)
    ap.add_argument('--no-growth',action='store_true',default=True,
                    help='do not exceed baseline size (default)')
    ap.add_argument('--allow-growth',action='store_false',dest='no_growth')
    return ap

if __name__=='__main__':run(cli().parse_args())
