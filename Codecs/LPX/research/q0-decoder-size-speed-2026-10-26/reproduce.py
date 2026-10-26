"""Verify golden PCM/PWM hashes, optionally rebuilding every complete AVR ELF.

Requires the ignored streams listed in streams.json (retained search caches),
the LPX Python dependencies, native g++, and optionally AVR-GCC + simavr.
Firmware, native libraries and raw timing traces belong in ignored build/.
"""
import argparse,hashlib,json,sys
from pathlib import Path

REPO=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools'))
from batch_decoder import BatchSession
from profile_avr import run as profile

def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root',type=Path,default=REPO,help='Root containing the ignored input caches')
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--native-only',action='store_true')
    ap.add_argument('--enable-asm',action='store_true')
    ap.add_argument('--avr-bin',type=Path);ap.add_argument('--sim-runner',type=Path)
    ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    ap.add_argument('--queue',type=int,default=512);ap.add_argument('--prefill',type=int,default=384)
    ap.add_argument('--dot-unroll',type=int,choices=(1,3,9),default=9)
    ap.add_argument('--irq-load',type=int,default=0)
    a=ap.parse_args()
    if not a.native_only and (a.avr_bin is None or a.sim_runner is None):
        ap.error('--avr-bin and --sim-runner are required for full AVR measurements')
    points=json.loads(Path(__file__).with_name('streams.json').read_text(encoding='utf-8'))
    unique={};a.output.mkdir(parents=True,exist_ok=True)
    with BatchSession('batch',v3_features=24) as decoder:
        for row in points:
            path=a.root/row['path'];blob=path.read_bytes();key=sha(blob)
            assert key==row['stream_sha256']
            if key not in unique:
                pcm=decoder.decode_one_s16(blob,row['samples']);pwm=decoder.decode_one(blob,row['samples'])
                assert pcm is not None and pwm is not None
                assert sha(pcm.astype('<i2').tobytes())==row['pcm16_sha256']
                assert sha(pwm.tobytes())==row['pwm_sha256']
                unique[key]=row
            else:
                for field in ('samples','pcm16_sha256','pwm_sha256'):assert unique[key][field]==row[field]
    report={'points':len(points),'unique_streams':len(unique),'native_pcm_pwm_exact':True,'images':{}}
    def save():
        (a.output/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save();print('Golden hashes exact:',len(points),'points,',len(unique),'streams',flush=True)
    if a.native_only:return
    for key,row in unique.items():
        r=profile(a.root/row['path'],a.output/key,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl,
            enable_asm=a.enable_asm,queue=a.queue,prefill=a.prefill,dot_unroll=a.dot_unroll,
            irq_load=a.irq_load,v3_features=24)
        assert r['pwm_sha256']==row['pwm_sha256']
        report['images'][key]={k:v for k,v in r.items() if k!='occupancy_trace'}
        save();print(len(report['images']),key,r['mean_decode_wall_cycles'],r['underruns'],flush=True)

if __name__=='__main__':main()
