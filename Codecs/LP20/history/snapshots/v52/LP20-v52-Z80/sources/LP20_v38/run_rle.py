import sys,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent; B=ROOT.parent
sys.path.insert(0,str(B/'LP20_v37'))
from reuse_macros import builder,np
import schedule_opt
import rle_builder as builder
orig=schedule_opt.choose; cache={}
def cached(acts,period,pulses,grid,emit):
    key=(tuple((t,k if not c else '',len(c)) for t,k,c in acts),period,pulses,tuple(grid))
    if key not in cache:cache[key]=orig(acts,period,pulses,grid,emit)
    return cache[key]
builder.share_tails.choose=cached
for clip in ('first','second'):
    p=B/'LP20_v37/release'/clip/'Strict8';out=ROOT/clip/'RLE';out.mkdir(parents=True,exist_ok=True)
    m=json.loads((p/'decoder.json').read_text());d=dict(np.load(p/'model.npz'));d['direct_start']=np.int32(int(d['direct_start'])-256);np.savez(out/'model.npz',**d);mm=builder.build(out/'model.npz',out/'decoder',period=320,grid=m['grid'],alpha=.001)
    assert mm['patterns']==m['patterns'];assert np.array_equal(np.load(out/'decoder.widths10.npy'),np.load(p/'decoder.widths10.npy'));assert (out/'decoder.expected').read_bytes()==(p/'decoder.expected').read_bytes()
    test=json.loads(subprocess.check_output([str(ROOT/'test_rle'),str(out/'decoder.bin'),str(out/'decoder.map'),str(out/'decoder.expected'),'320','8','0','16',str(out/'decoder.threads')],text=True));test.update(core_bytes=mm['used']-mm['stream_bytes'],occupied_rom=mm['used'],stream_bytes=mm['stream_bytes'],core_saved=m['used']-mm['used']);(out/'test.json').write_text(json.dumps(test,indent=2));print(clip,test,flush=True)
