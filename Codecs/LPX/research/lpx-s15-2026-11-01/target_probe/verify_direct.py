"""Portable replay of the direct-parser contracts; no encoder fitting."""
from pathlib import Path
import os,sys,json,subprocess,hashlib,time,argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--repo',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--input',type=Path,required=True)
ap.add_argument('--compiler',required=True)
ap.add_argument('--legacy-expansion-dir',type=Path)
a=ap.parse_args()
P=a.output.resolve();TASK=a.repo.resolve()
if TASK/'build' not in P.parents:raise ValueError('Output must be under repository build/')
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[key]='1'
os.environ['NUMBA_CACHE_DIR']=str(P/'numba-cache')
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(TASK/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools')]
import numpy as np
from numba import njit
from batch_decoder import BatchDecoder
from s15_format import expand,decode_model,pack,unpack
from test_s15 import fixture
from s15_native import Native
import speech_compact as v5
from q0_model import clamp,cdiv,_trace_poly_mul,table,synthesize
from standard_metrics import pwm_duties
CC=a.compiler
base=['-O2','-std=c++11','-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_ENABLE_ASM=0']

@njit(cache=True)
def coefficient_grid(vectors,n,segments,cosine):
    result=np.empty((n,10),np.int64);ends=np.empty((segments+1,10),np.int64)
    polys=np.empty((2,12),np.int64);width=16//segments;subs=8//segments
    for fi in range(len(vectors)):
        old=vectors[max(0,fi-1)];cur=vectors[fi]
        for point in range(segments+1):
            t=point*width;polys[:,:]=0;polys[0,0]=polys[0,1]=4096
            polys[1,0]=4096;polys[1,1]=-4096
            for i in range(10):
                norm=(old[i]*(16-t)+cur[i]*t)>>2;idx=norm>>4;frac=norm&15
                c=-(cosine[idx]+((cosine[idx+1]-cosine[idx])*frac>>4));p=polys[i%2];degree=2+(i//2)*2
                p[degree+1]=p[degree-1];p[degree]=p[degree-2]+_trace_poly_mul(p[degree-1],c)
                for j in range(degree-1,1,-1):p[j]=p[j-2]+_trace_poly_mul(p[j-1],c)+p[j]
                p[1]=_trace_poly_mul(p[0],c)+p[1]
            for k in range(10):ends[point,k]=clamp(cdiv(polys[0,k+1]+polys[1,k+1],2))
        for sub in range(8):
            local=(sub*2+1)%width;start=fi*160+sub*20;end=min(n,start+20)
            for k in range(10):
                a=ends[sub//subs,k];b=ends[sub//subs+1,k];value=clamp(a+cdiv((b-a)*local,width))
                for at in range(start,end):result[at,k]=value
    return result

def model(blob,segments):
    n,profile,spectra,params,pulses,pre,bright,extras=v5.unpack(blob)
    shift=5 if profile==4 else 4
    vectors=np.asarray([[(int(v)<<shift)+(1<<(shift-1)) for v in row] for row in spectra for _ in range(2)],np.int64)
    co=coefficient_grid(vectors[:(n+159)//160],n,segments,table('cos_table.inc'))
    q=[];scales=[]
    for half,(scale,lag,gain) in enumerate(params):
        scales.extend([scale*8]*2)
        for si in range(8):
            pos,amp=pulses[half*8+si]
            for j in range(20):
                at=len(q);ep,ea=extras[at//40];pred=(gain*(q[-lag] if at>=lag else 0)+8)>>4
                q.append(min(31,max(-32,pred+(amp if j==pos else 0)+(ea if at%40==ep else 0))))
    return synthesize(np.asarray(q[:n],np.int64),np.asarray(scales,np.int64),co,table('scale_table.inc'),pre,bright)

def compile_lib(stem,source,flags):
    out=P/(stem+'.so');cmd=[CC,*base,*flags,'-shared','-fPIC','-I'+str(source),str(source/'Lpx4HybridCore.cpp'),str(source/'native_batch_decoder.cpp'),'-o',str(out)]
    r=subprocess.run(cmd,capture_output=True);(P/(stem+'-build-private.log')).write_bytes(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('Native compilation failed: '+stem)
    return BatchDecoder(out)

started=time.perf_counter();checks=0;tail_checks=0;malformed_checks=0;copy_checks=0
actual=a.input.read_bytes()
cases=[actual]+[fixture(n) for n in (1,19,20,79,80,81,159,160,319,320,321,641)]
v5cases=[(TASK/'web-player/audio/lpx-bread'/name).read_bytes() for name in ('compact.lpx','quality.lpx')]
rows=[]
for segments in (2,1,4):
    seg=[f'-DLPX3_LPC_SEGMENTS={segments}']
    common=compile_lib(f'common-s{segments}',P/'baseline',seg)
    compact=compile_lib(f'v5-s{segments}',P/'baseline',seg+['-DLPX4_COMPACT_ONLY=1'])
    for memory in (0,1):
        flags=seg+['-DLPX4_COMPACT_ONLY=1','-DLPX4_ENABLE_S15=1',f'-DLPX4_MEMORY_PROFILE={memory}']
        direct=compile_lib(f'direct-m{memory}-s{segments}',P/'src',flags)
        for blob in cases:
            n=int.from_bytes(blob[8:12],'little');expanded=expand(blob);expected=model(expanded,segments)
            if segments==2:assert np.array_equal(expected,decode_model(blob))
            outputs=[direct.decode_one_s16(blob,n),common.decode_one_s16(expanded,n),compact.decode_one_s16(expanded,n)]
            for pcm in outputs:assert pcm is not None and np.array_equal(pcm,expected);checks+=1
            for decoder,stream in ((direct,blob),(common,expanded),(compact,expanded)):
                out=decoder.decode_one(stream,n);assert out is not None and np.array_equal(out,pwm_duties(expected));checks+=1
            assert compact.decode_one_s16(blob,n) is None and common.decode_one_s16(blob,n) is None
            if blob==actual and segments==2:
                for name in (('common.so','v5-only.so') if a.legacy_expansion_dir else ()):
                    old=Native(a.legacy_expansion_dir/name)
                    assert np.array_equal(old.decode(blob,n),expected)
                    assert np.array_equal(old.decode(blob,n,True),pwm_duties(expected));checks+=2
                (P/f'actual-m{memory}-expected.pwm').write_bytes(pwm_duties(expected).tobytes())
        for blob in v5cases:
            n=int.from_bytes(blob[8:12],'little');expected=model(blob,segments)
            for method,ref in (('decode_one_s16',expected),('decode_one',pwm_duties(expected))):
                got=getattr(direct,method)(blob,n);assert got is not None and np.array_equal(got,ref);checks+=1
        for complete in (320,640):
            blob=fixture(complete);expected=model(expand(blob),segments)
            for n in range(complete-319,complete+1):
                tail=bytearray(blob);tail[8:12]=n.to_bytes(4,'little');tail=bytes(tail)
                pcm=direct.decode_one_s16(tail,n);pwm=direct.decode_one(tail,n)
                assert pcm is not None and np.array_equal(pcm,expected[:n])
                assert pwm is not None and np.array_equal(pwm,pwm_duties(expected[:n]));tail_checks+=2
        invalid=[]
        for n in (1,20,79,80,159,160,319,320):
            blob=fixture(n)
            for cut in (1,2,3):
                bad=bytearray(blob[:-cut]);bad[20:22]=(len(bad)-22).to_bytes(2,'little');invalid.append((n,bytes(bad)))
            bad=bytearray(blob);bad.append(0);bad[20:22]=(len(bad)-22).to_bytes(2,'little');invalid.append((n,bytes(bad)))
            args=unpack(blob);_,meta=pack(*args)
            if meta['padding_bits']:
                bad=bytearray(blob);bad[-1]|=128;invalid.append((n,bytes(bad)))
        for offset in (4,5,6,16,18):
            bad=bytearray(actual);bad[offset]^=1;invalid.append((19200,bytes(bad)))
        for blob in v5cases:
            bad=bytearray(blob);bad[5]|=64;invalid.append((19200,bytes(bad)))
        for n,blob in invalid:assert direct.decode_one_s16(blob,n) is None;malformed_checks+=1
        exe=P/f'copy-m{memory}-s{segments}.exe'
        cmd=[CC,*base,*flags,'-I'+str(P/'src'),str(TASK/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/anchor_copy.cpp'),str(P/'src/Lpx4HybridCore.cpp'),'-o',str(exe)]
        r=subprocess.run(cmd,capture_output=True);(P/f'copy-m{memory}-s{segments}-build-private.log').write_bytes(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('Copy build failed')
        for path in (a.input.resolve(),):
            r=subprocess.run([str(exe),str(path)],capture_output=True);assert r.returncode==0;copy_checks+=1
        rows.append(dict(segments=segments,memory_profile=memory,status='PASS'))
        print(json.dumps(rows[-1]),flush=True)
proof=json.loads((P/'source-private.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert all(sha(P/'baseline'/name)==digest for name,digest in proof['baseline'].items())
assert all(sha(P/'src'/name)==digest for name,digest in proof['prototype'].items())
result=dict(status='PASS',rows=rows,full_domain_comparisons=checks,partial_tail_domain_comparisons=tail_checks,
            malformed_rejections=malformed_checks,copy_probe_invocations=copy_checks,wall_seconds=time.perf_counter()-started)
(P/'native-proof-private.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
