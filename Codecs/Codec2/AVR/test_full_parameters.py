import sys,ctypes,subprocess,random
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'Codec2_Tiny13_Quality_R2'/'tests'))
from codec2_test_common import fields
class Param(ctypes.Structure):
    _fields_=[('voiced',ctypes.c_uint8*2),('pitch_index',ctypes.c_uint8),('energy_index',ctypes.c_uint8),('lspd_index',ctypes.c_uint8*10),('lsp_25hz',ctypes.c_uint16*10)]
so=root/'build'/'parameters_host.so';so.parent.mkdir(exist_ok=True)
subprocess.run(['gcc','-O2','-std=c99','-fPIC','-shared','-Wall','-Wextra','-Werror',str(root/'codec2_3200_full_parameters.c'),'-o',str(so)],check=True)
f=ctypes.CDLL(str(so)).codec2_params_3200
f.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.POINTER(Param)]
paths=[root/'Codec2_Tiny13_Quality_R2'/'tests'/name for name in ('speech.c2zx','codec2_3200_8byte_frames.bin')]
rng=random.Random(0xC02DEC2)
count=0
for data in [*[p.read_bytes()[i:i+8] for p in paths for i in range(0,p.stat().st_size,8)],*[rng.randbytes(8) for _ in range(10000)]]:
    assert len(data)==8
    a=Param();f((ctypes.c_uint8*8).from_buffer_copy(data),ctypes.byref(a))
    v0,v1,p,e,ls=fields(data)
    assert (a.voiced[0],a.voiced[1],a.pitch_index,a.energy_index,list(a.lspd_index))==(v0,v1,p,e,ls)
    freq=[];c=0
    for i,index in enumerate(ls):
        c+=2*index-6 if 3<=i<=5 and index>=8 else index+1
        freq.append(c)
    assert list(a.lsp_25hz)==freq
    count+=1
print('PASS',count,'standard Codec2-3200 frames, all 10 LSPD indices and cumulative frequency values')
