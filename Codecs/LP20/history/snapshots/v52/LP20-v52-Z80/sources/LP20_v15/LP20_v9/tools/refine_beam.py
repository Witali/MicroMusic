"""Refine the excitation vectors using the three-history search result, then rerun trellis."""
from experiment import *
from beam_vbr import main
if __name__=='__main__':
 d=np.load(sys.argv[1]);z={k:d[k] for k in d};t,tb,bk,bm,lens,idx=[z[k] for k in ('target','tb','bk','bm','lens','idx')];y,h,over=reconstruct(t,tb,bk,bm,lens,idx);w=(uniform_filter1d(t*t,size=156)+12.)**(-.12);w/=w.mean();z['bk']=train_refine(t,tb,bk,bm,lens,idx,h,w);out=ROOT/'refined_seed.npz';np.savez(out,**z);main(str(out),'refined_beam',4,.12,.5,30.5)
