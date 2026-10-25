#!/usr/bin/env python3
from pathlib import Path
import struct, hashlib
HERE=Path(__file__).resolve().parent
img=(HERE/'codec2zx.trd').read_bytes(); code=(HERE/'codec2zx.bin').read_bytes()
assert len(img)==655360
ent=img[:16]
name=ent[:8].decode('ascii'); typ=chr(ent[8]); load=struct.unpack('<H',ent[9:11])[0]
ln=struct.unpack('<H',ent[11:13])[0]; nsec=ent[13]; sec=ent[14]; trk=ent[15]
di=8*256
free=struct.unpack('<H',img[di+229:di+231])[0]
assert name=='C2DEMO  ' and typ=='C' and load==0x8000 and ln==len(code)
assert nsec==12 and sec==0 and trk==1
assert img[di+227]==0x16 and img[di+228]==1 and img[di+231]==0x10
start=(trk*16+sec)*256
assert img[start:start+ln]==code
print('TRD VALIDATION OK')
print({'name':name,'type':typ,'load':load,'length':ln,'sectors':nsec,'start_track':trk,'start_sector':sec,'free_sectors':free,'label':img[di+245:di+253].decode('ascii')})
print('sha256',hashlib.sha256(img).hexdigest())
