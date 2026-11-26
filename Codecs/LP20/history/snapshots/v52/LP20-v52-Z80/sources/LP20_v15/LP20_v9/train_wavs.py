#!/usr/bin/env python3
"""Fit a shared dictionary from your training WAV files; keep test audio out."""
import argparse
import numpy as np
import study as s
from balanced import train_balanced
p=argparse.ArgumentParser();p.add_argument('wav',nargs='+');p.add_argument('--out',required=True);p.add_argument('--balanced',action='store_true');a=p.parse_args();inp=[s.load(f) for f in a.wav];ww=np.load(s.ROOT/'pooled_model.npz')['ww'];m=(train_balanced if a.balanced else s.train_model)(inp,ww);np.savez(a.out,**m)
