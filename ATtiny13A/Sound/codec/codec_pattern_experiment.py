#!/usr/bin/env python3
"""Offline comparison of frequency/formant pattern dictionaries and parameter coding.
Not a firmware: uses same 8-bit arithmetic DSP model as v4 AVR, for apples-to-apples.
"""
from pathlib import Path
import numpy as np, soundfile as sf
from sklearn.cluster import KMeans
from model_exact import synth_exact
from spectral_objective import evaluate, x
P=Path(__file__).resolve().parent
z=np.load(P/'best_parameters.npz'); K=z['K'].astype(np.int64);PITCH=z['P'].astype(np.int64); E=z['E'].astype(np.int64)
L=256*len(PITCH)
base=synth_exact(K,PITCH,E,L)
print('v4',evaluate(base[:len(x)]/128,True),'max diff',int(np.abs(np.diff(base)).max()),flush=True)
# Use same 5 B/frame baseline. K quantized per group of 7 * 4 bit.
# codebook dictionary entry stores seven int4s (four bytes), each frame stores 8-bit F0 and 4-bit gain plus 4-bit dictionary ID.
for n in [4,8,16,24,32,48]:
 for style in ['plain','weighted']:
  km=KMeans(n_clusters=n,n_init=18,random_state=7, max_iter=600)
  w=(0.3+E.astype(float)/6)**2
  km.fit(K,sample_weight=w if style=='weighted' else None)
  centers=np.clip(np.rint(km.cluster_centers_),-7,7).astype(np.int64)
  idx=km.labels_
  newK=centers[idx]
  y=synth_exact(newK,PITCH,E,L)
  m=evaluate(y[:len(x)]/128,True)
  bitsid=int(np.ceil(np.log2(n)))
  size=4*n+87+int(np.ceil((bitsid+4)*len(E)/8))
  # Variant with P/E 2 bytes, K indices packed as 4 bit for 16 patterns
  print(f'codebook {n:2d} {style:8s} total={size:3d}B spectral={m["spectral_mel_distance"]:.3f} stoi={m["stoi"]:.3f} loud={m["loudness_envelope_error"]:.3f} K_mae={np.abs(K-newK).mean():.2f} clicks>=60={np.sum(np.abs(np.diff(y))>=60)}',flush=True)
  np.savez(P/f'palette{n}_{style}.npz',K=centers,idx=idx)
