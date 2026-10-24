#!/usr/bin/env python3
"""Save measured comparison of installed original libspeex vs unchanged R4.
Not a validation of the yet-unbuilt patched upstream source.
"""
from pathlib import Path
import subprocess
import csv
import wave
import struct
from decode_with_system_speex import decode, metrics
R=Path(__file__).resolve().parents[1]
data=R/'baseline_R4/Speex_AVR_LSP_R4/data'
exe=R/'baseline_R4/Speex_AVR_LSP_R4/src/host_decode'
if not exe.exists():
    src=exe.parent
    subprocess.run(['make','host'],cwd=src,check=True)
rows=[]
for file in sorted(data.glob('*.spxraw')):
    tmp=R/'results'/('tmp_r4_'+file.stem+'.wav')
    subprocess.run([str(exe),str(file),str(tmp)],check=True,capture_output=True)
    with wave.open(str(tmp),'rb') as w:
        b=struct.unpack('<%dh'%w.getnframes(),w.readframes(w.getnframes()))
    a=decode(file.read_bytes())
    m=metrics(a,b)
    rows.append({'file':file.name,'frames':file.stat().st_size//20,
                 'samples':m['samples'],'identical_samples':m['identical'],
                 'snr_db':format(m['SNR_dB'],'.4f'),
                 'corr':format(m['corr'],'.9f') if m['corr'] is not None else ''})
    tmp.unlink()
out=R/'results'/ 'reference_libspeex_vs_R4.csv'
with out.open('w',newline='') as f:
    dw=csv.DictWriter(f,fieldnames=rows[0]);dw.writeheader();dw.writerows(rows)
print('Saved comparison',out,'streams',len(rows),'frames',sum(x['frames'] for x in rows))
for row in rows:print(row['file'],row['snr_db'],'dB')
