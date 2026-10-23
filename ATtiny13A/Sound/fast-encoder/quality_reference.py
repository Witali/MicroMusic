"""Reference Python implementation for C regression tests, not hot-path encoding."""
import numpy as np
from pystoi import stoi

class ReferenceMetrics:
    def __init__(self,ref):
        self.ref=np.asarray(ref,dtype=np.float32)
        self.log=self.stft_log(self.ref)
    @staticmethod
    def stft_log(x):
        x=np.asarray(x)
        if x.dtype.kind in 'ui':x=(x.astype(np.float32)-128.)/128.
        else:x=x.astype(np.float32)
        x=np.pad(x,(128,128))
        blocks=np.lib.stride_tricks.sliding_window_view(x,256)[::128]
        ft=np.fft.rfft(blocks*np.hanning(256).astype(np.float32),axis=-1)
        return np.log(np.maximum(np.abs(ft),0.006)).astype(np.float32)
    def scores(self,x):
        x=np.asarray(x,np.uint8)
        st=float(stoi(self.ref,(x.astype(np.float32)-128)/128,7500,extended=False))
        spec=float(np.mean(np.abs(self.stft_log(x)-self.log)))
        clicks=int(np.sum(abs(np.diff(x.astype(int)))>=48))
        return (st,spec,clicks)
