import numpy as np
from scipy.signal import get_window
from pystoi import stoi
SR=7500

def stft_log(x):
    x=np.asarray(x)
    if x.dtype.kind in 'ui':x=(x.astype(np.float32)-128.0)/128.0
    else:x=x.astype(np.float32)
    x=np.pad(x,(128,128))
    blocks=np.lib.stride_tricks.sliding_window_view(x,256)[::128]
    ft=np.fft.rfft(blocks*np.hanning(256).astype(np.float32),axis=-1)
    log=np.log(np.maximum(np.abs(ft),0.006))
    return log.astype(np.float32)

def score_stoi(ref,x):
    x=np.asarray(x,dtype=np.float32)
    return float(stoi(ref,(x-128)/128,SR,extended=False))

class Compare:
    def __init__(self,ref):
        self.ref=np.asarray(ref,dtype=np.float32)
        self.log=stft_log(self.ref)
        self.weight=np.clip(np.linalg.norm(self.log[:,:],axis=1),1,999)
    def spec(self,x):
        z=stft_log(np.asarray(x,dtype=np.uint8))
        return float(np.mean(np.abs(z-self.log)))
    def scores(self,x):
        x=np.asarray(x,np.uint8)
        return score_stoi(self.ref,x),self.spec(x),int(np.sum(abs(np.diff(x.astype(int)))>=48))
