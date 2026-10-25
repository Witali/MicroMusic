#!/usr/bin/env python3
"""Create a full 80-track double-sided TR-DOS .TRD image with C2DEMO.C."""
from pathlib import Path
import struct, math
HERE=Path(__file__).resolve().parent
code=(HERE/'codec2zx.bin').read_bytes()
LOAD=0x8000
NAME=b'C2DEMO  '          # exactly 8 chars
FTYPE=ord('C')
SECTOR=256
SPT=16
LOGICAL_TRACKS=160       # 80 tracks * 2 sides, alt ordering
TOTAL_SECTORS=LOGICAL_TRACKS*SPT
IMAGE_SIZE=TOTAL_SECTORS*SECTOR
img=bytearray(IMAGE_SIZE)

nsec=(len(code)+SECTOR-1)//SECTOR
start_track=1            # logical track 1 (side 1, physical track 0)
start_sector=0

# Directory entry 0, track 0 sector 0.
ent=bytearray(16)
ent[0:8]=NAME
ent[8]=FTYPE
ent[9:11]=struct.pack('<H',LOAD)
ent[11:13]=struct.pack('<H',len(code))
ent[13]=nsec
ent[14]=start_sector
ent[15]=start_track
img[0:16]=ent

# Disk info lives in track0 sector8 (physical sector9 in TR-DOS terminology).
di=8*SECTOR
next_linear=start_track*SPT+start_sector+nsec
next_track=next_linear//SPT
next_sector=next_linear%SPT
img[di+225]=next_sector
img[di+226]=next_track
img[di+227]=0x16         # 80 tracks, double sided
img[di+228]=1            # file count
free=TOTAL_SECTORS-16-nsec  # whole logical track0 is reserved
img[di+229:di+231]=struct.pack('<H',free)
img[di+231]=0x10         # TR-DOS signature/id
img[di+233:di+242]=b' '*9
img[di+244]=0
img[di+245:di+253]=b'CODEC2ZX'

# File sectors are contiguous starting at logical track1 sector0.
data_off=(start_track*SPT+start_sector)*SECTOR
img[data_off:data_off+len(code)]=code

out=HERE/'codec2zx.trd'
out.write_bytes(img)
print(f'wrote {out.name}: {len(img)} bytes; C2DEMO.C {len(code)} bytes, {nsec} sectors; free={free}')
