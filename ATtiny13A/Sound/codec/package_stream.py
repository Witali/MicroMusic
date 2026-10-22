"""Pack v4 jointly optimized LPC parameters. Original format untouched (5 bytes/frame)."""
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parent
z=np.load(P/'best_parameters.npz');K=z['K'];pitch=z['P'];E=z['E']
assert K.shape==(87,7) and len(E)==len(pitch)==87
stream=bytearray()
for i in range(len(pitch)):
 k=K[i].astype(int); pi=int(pitch[i]); gain=int(E[i]);
 assert all(-7<=n<=7 for n in k),k
 assert 0<=pi<=254 and 0<=gain<=15
 stream.extend([pi,(gain&15)|((k[0]+8)<<4),((k[2]+8)<<4)|(k[1]+8),((k[4]+8)<<4)|(k[3]+8),((k[6]+8)<<4)|(k[5]+8)])
(P/'voice_tinylpc.bin').write_bytes(stream)
print('Speech',len(stream),'bytes frames',len(stream)//5)
print('Pitch',list(pitch))
print('E',list(E))
