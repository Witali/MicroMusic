#!/usr/bin/env python3
"""Reproducible numerical regressions for the C encoder and its format."""
import argparse,json,subprocess
import numpy as np,soundfile as sf
from pathlib import Path
from fast_train import HERE,Native,SOURCE,unpack_stream,pack_stream,python_metrics
from quality_reference import ReferenceMetrics

def main():
    p=argparse.ArgumentParser();p.add_argument('--voices',nargs='*',default=['demo']);a=p.parse_args()
    result={}
    for name in a.voices:
        loc=SOURCE/name
        f,d=unpack_stream((loc/'speech.hq').read_bytes())
        assert pack_stream(f,d)==(loc/'speech.hq').read_bytes()
        ref,sr=sf.read(loc/'original.wav');assert sr==7500 and len(ref)==int(d.sum())
        core=Native(ref)
        try:
            y=core.decode(f,d)
            c=core.metrics(y)
            py=ReferenceMetrics(ref).scores(y)
            assert np.allclose(c,py,atol=1e-6,rtol=1e-6),(name,c,py)
            result[name]={"frames":len(f),"samples":len(y),"stoipy":py[0],"stoic":float(c[0]),"spec":float(c[1]),"mismatch":0}
        finally:core.close()
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
