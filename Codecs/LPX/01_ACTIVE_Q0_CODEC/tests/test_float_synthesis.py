"""Independent scalar-double DSP, shared-parser and fixed-default contracts."""
from pathlib import Path
import array,ctypes as ct,json,math,struct,subprocess,time,shutil,sys,tempfile,unittest

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'
OUT=None
ROWS=[]
CONFIGS=[(9,0,0,1,1,2,1,1),(9,1,0,0,0,1,0,0),
    (9,0,1,1,0,4,1,0),(9,1,1,0,1,2,0,1),
    (5,0,0,1,1,2,1,1),(5,1,1,0,0,4,0,0),(5,0,0,1,1,2,1,1,0)]

def compile_lib(config,floating=True):
    version,memory,ring,q4,rotate,segments,pointer,batch=config[:8]
    only=config[8] if len(config)>8 else 1
    name=('float-' if floating else 'fixed-')+'-'.join(map(str,config))
    target=OUT/(name+'.so')
    flags=dict(LPX4_FLOAT_SYNTHESIS=int(floating),LPX4_ENABLE_ASM=0,LPX4_ENABLE_SPEECH=1,
        LPX4_ENABLE_SPEECH_COMPACT=1,LPX4_COMPACT_ONLY=only,LPX4_COMPACT_VERSION=version,
        LPX4_ENABLE_SPARSE80=int(version==5 and only),LPX4_MEMORY_PROFILE=memory,LPX4_LPC_RING=ring,
        LPX4_EXCITATION_Q4=q4,LPX4_ROTATE_LPC_ANCHORS=rotate,LPX3_LPC_SEGMENTS=segments,
        LPX4_ROM_POINTER=pointer,LPX4_BATCHED_REMAINING=batch,LPX4_ENABLE_INPUT_CALLBACK=1)
    command=['g++','-O2','-shared','-fPIC','-std=c++11','-ffp-contract=off']
    command+=['-D%s=%d'%item for item in flags.items()]
    command+=['-I'+str(SRC),str(OUT/'float-core-native.cpp'),str(SRC/'Lpx4HybridCore.cpp'),'-o',str(target)]
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr)
    lib=ct.CDLL(str(target));lib.object_size.restype=ct.c_uint32
    lib.decode.argtypes=[ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint32,ct.c_int16,ct.c_uint8,
        ct.POINTER(ct.c_double),ct.c_uint32,ct.POINTER(ct.c_uint32),ct.POINTER(ct.c_double)]
    lib.decode.restype=ct.c_int
    return lib

def decode(lib,blob,n,mode=0,available=None,failure=-1):
    raw=(ct.c_uint8*len(blob)).from_buffer_copy(blob);out=(ct.c_double*(n+1))()
    meta=(ct.c_uint32*7)();diagnostics=(ct.c_double*3)()
    count=lib.decode(raw,len(blob),len(blob) if available is None else available,failure,
        mode,out,n+1,meta,diagnostics)
    assert count>=0
    return list(out[:count]),tuple(meta),tuple(diagnostics)

def clamp(x,lo,hi):return min(hi,max(lo,x))

def polynomial(lsf):
    # Independent direct convolution, not the decoder's in-place recurrence.
    polynomials=[]
    for parity in (0,1):
        p=[1.0,1.0 if not parity else -1.0]
        for i in range(parity,10,2):
            factor=-2.0*math.cos(math.pi*lsf[i]);expanded=[0.0]*(len(p)+2)
            for j,value in enumerate(p):
                expanded[j]+=value;expanded[j+1]+=factor*value;expanded[j+2]+=value
            p=expanded
        polynomials.append(p)
    return [clamp((polynomials[0][i+1]+polynomials[1][i+1])*0.5,-32767/4096,32767/4096) for i in range(10)]

def reference(row,segments,ring):
    n=row['samples'];bins=32 if row['profile']==4 else 64
    spectra=[[(x+0.5)/bins for x in vec] for vec in row['spectra']]
    history=[0.0]*10;dd=0.0;out=[];anchors={};width=16//segments;sps=8//segments
    coefficient_fraction=0.0;history_fraction=0.0
    for at in range(n):
        if at%20==0:
            fi=at//320;half=(at//160)%2;sub=(at//20)%8;left=(sub//sps)*width
            def anchor(t):
                key=(fi,half,t)
                if key not in anchors:
                    current=spectra[fi];previous=current if half else spectra[max(0,fi-1)]
                    lsf=[a+(b-a)*(t/16.0) for a,b in zip(previous,current)]
                    anchors[key]=polynomial(lsf)
                return anchors[key]
            first,last=anchor(left),anchor(left+width);t=(2*sub+1)%width
            co=[a+(b-a)*(t/width) for a,b in zip(first,last)]
            coefficient_fraction=max(coefficient_fraction,max(abs(x*4096-round(x*4096)) for x in co))
        pred=float(row['q'][at]*row['steps'][at])
        for i in (range(10) if ring else range(9,-1,-1)):pred-=co[i]*history[i]
        pred=clamp(pred,-32767.0,32767.0);history=[pred]+history[:9]
        previous=clamp(dd,-16384.0,16384.0)
        dd=clamp(pred+(row['pre']/16384.0)*dd,-32767.0,32767.0)
        value=clamp(clamp(dd,-16384.0,16384.0)-(row['bright']/16384.0)*previous,-16384.0,16384.0)
        history_fraction=max(history_fraction,abs(dd-round(dd)))
        out.append(value/16384.0)
    return out,coefficient_fraction,history_fraction

def main():
    started=time.perf_counter();cases=0;max_error=0.0;fractional=0;details=[];cache={}
    for config in CONFIGS:
        lib=compile_lib(config);version,memory,ring,q4,rotate,segments,pointer,batch=config[:8]
        only=config[8] if len(config)>8 else 1
        matching=[r for r in ROWS if (r['version']==9)==(version==9)]
        if not only:matching=[r for r in matching if r['version']==5]
        config_error=0.0
        for row in matching:
            folder=OUT/'fixtures'/('%03d'%row['index']);blob=(folder/'stream.lpx').read_bytes();n=row['samples']
            key=(row['index'],segments,ring)
            expected,cf,hf=reference(row,segments,ring)
            actual,meta,diag=decode(lib,blob,n)
            assert meta[:5]==(1,0,n,n,1),(config,row['index'],meta)
            assert len(actual)==n and all(math.isfinite(x) and -1<=x<=1 for x in actual)
            error=max(abs(a-b) for a,b in zip(actual,expected))
            assert error<1e-10,(config,row['index'],error)
            config_error=max(config_error,error);max_error=max(max_error,error)
            if diag[0]>1e-6 and cf>1e-6:fractional+=1
            callback,cm,_=decode(lib,blob,n,mode=1)
            assert callback==actual and cm[:5]==meta[:5] and cm[5]==cm[6]<=len(blob)
            if n==641:
                for mode in (2,3,5):
                    reset,rm,_=decode(lib,blob,n,mode=mode)
                    assert reset==actual and rm[:5]==meta[:5]
            cases+=2
        details.append(dict(config=config,streams=len(matching),maximum_reference_error=config_error,
            object_bytes=lib.object_size()))
        print(json.dumps(details[-1]),flush=True)
    # Float mode must retain the existing parser's truncation/EOF rejection.
    lib=compile_lib(CONFIGS[0]);row=next(r for r in ROWS if r['version']==9 and r['samples']==641)
    blob=(OUT/'fixtures'/('%03d'%row['index'])/'stream.lpx').read_bytes();invalid=0
    for at in range(len(blob)):
        actual,meta,_=decode(lib,blob[:at],641)
        assert not meta[0] or meta[1] or len(actual)!=641
        invalid+=1
    trailing=bytearray(blob+b'\0');trailing[11:13]=struct.pack('<H',len(trailing)-13)
    actual,meta,_=decode(lib,bytes(trailing),641);assert meta[1] and not meta[4];invalid+=1
    pad=bytearray(blob);pad[-1]|=128
    actual,meta,_=decode(lib,bytes(pad),641);assert meta[1] and not meta[4];invalid+=1
    for available in (0,3,12,len(blob)-1):
        for failure in (-1,-2,256):
            actual,meta,_=decode(lib,blob,641,1,available,failure)
            assert meta[1] and meta[5]<=available+1 and meta[6]==available
            invalid+=1
    _,meta,_=decode(lib,blob,641,4);assert not meta[0] and meta[1] and not meta[5];invalid+=1
    fixed_cases=0
    summary=dict(schema='lpx-floating-core-private-v1',float_decodes=cases,configs=details,
        fractional_state_and_coeff_cases=fractional,maximum_reference_error=max_error,
        malformed_cases=invalid,fixed_default_exact_streams=fixed_cases,
        elapsed_seconds=time.perf_counter()-started,quality_improvement_claim=False)
    (OUT/'core-test-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary),flush=True)




def make_fixtures():
    sys.path.insert(0,str(ROOT/'tools'))
    from test_sram512_profile import fixture
    from test_speech_v9 import sparse_fixture
    from speech_v9 import repack
    scales=[0,0,0,0,0,0,1,1,1,1,2,3,4,6,8,12,16,23,33,46,66,93,131,185,262,371,524,741,1049,1483,2097,2966]
    rows=[]
    for profile in (4,6,15):
        for n in (1,19,20,39,40,79,80,81,159,160,161,319,320,321,641,1280,64000):
            frames=(n+319)//320;params=[];pulses=[];extras=[]
            if profile==15:
                old,_=sparse_fixture(n,'changing',16383,11468,18)
                spectra=[[3+5*i+(fi%2) for i in range(10)] for fi in range(frames)]
                pre,bright=16383,11468
                pulses=[(0,0)]*(frames*16);extras=[(-1,0)]*(frames*8)
                for fi in range(frames):
                    params.extend([(24+fi%8,18,(fi%8)*2)]*2)
                    for group in range(4):
                        index=fi*4+group;code=(index*13)%64;position=code+(code+2)//4
                        amp=-8 if (index//64)%2 else 7
                        pulses[index*4+position//20]=(position%20,amp)
            else:
                old=fixture(profile,n,18,extras=True)
                spectra=[[2+2*i+fi%2 for i in range(10)] for fi in range(frames)]
                pre,bright=8192,11469
                for fi in range(frames):
                    for half in range(2):
                        params.append((20+(fi*2+half)%4,18,14))
                        for group in range(4):
                            index=fi*8+half*4+group
                            for pulse in range(2):
                                if profile==4:
                                    code=(index*2+pulse)%16;position=code+(code+2)//4
                                    amp=8 if pulse else -8
                                else:
                                    position=(index*2+pulse)%20
                                    amp=7-index%16 if pulse else index%16-8
                                pulses.append((position,amp))
                            extras.append((index%40,-8 if index&1 else 7))
            q=[];steps=[]
            for half,(scale,lag,gain) in enumerate(params):
                for si in range(8):
                    pos,amp=pulses[half*8+si]
                    for j in range(20):
                        at=len(q);ep,ea=extras[at//40]
                        prediction=(gain*(q[-lag] if at>=lag else 0)+8)>>4
                        q.append(min(31,max(-32,prediction+(amp if j==pos else 0)+(ea if at%40==ep else 0))))
                        steps.append(scales[scale])
            for blob in (old,repack(old)[0]):
                index=len(rows);folder=OUT/'fixtures'/('%03d'%index);folder.mkdir(parents=True)
                (folder/'stream.lpx').write_bytes(blob)
                rows.append(dict(index=index,samples=n,profile=4 if profile==4 else 6,
                    spectra=spectra,pre=pre,bright=bright,q=q[:n],steps=steps[:n],
                    version=9 if blob[:2]==b'L9' else blob[4]))
    return rows

class FloatingSynthesisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global OUT,ROWS
        cls.folder=tempfile.TemporaryDirectory(prefix='lpx-float-dsp-')
        OUT=Path(cls.folder.name)
        shutil.copyfile(ROOT/'tests/float_synthesis_native.cpp',OUT/'float-core-native.cpp')
        ROWS=make_fixtures()

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def test_independent_double_reference_parser_fractional_state_and_tails(self):
        main()

    def test_only_final_adapters_quantize_and_preserve_double_state(self):
        lib=compile_lib(CONFIGS[0])
        fn=lib.decode_adapter
        fn.argtypes=[ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint8,
            ct.POINTER(ct.c_double),ct.c_uint32,ct.POINTER(ct.c_uint32),ct.POINTER(ct.c_double)]
        fn.restype=ct.c_int
        for row in ROWS:
            if row['version']!=9 or row['samples']!=641:continue
            blob=(OUT/'fixtures'/('%03d'%row['index'])/'stream.lpx').read_bytes()
            raw=(ct.c_uint8*len(blob)).from_buffer_copy(blob);domains=[];states=[]
            for domain in range(4):
                values=(ct.c_double*642)();meta=(ct.c_uint32*4)();state=(ct.c_double*11)()
                count=fn(raw,len(blob),domain,values,642,meta,state)
                self.assertEqual(count,641);self.assertEqual(tuple(meta),(1,0,1,641))
                domains.append(list(values[:count]));states.append(tuple(state))
            self.assertTrue(all(state==states[0] for state in states))
            self.assertEqual(domains[1],[clamp(math.floor(x*32768+0.5),-32768,32767) for x in domains[0]])
            self.assertEqual(domains[2],[clamp(128+math.floor(x*130+0.5),0,255) for x in domains[0]])
            self.assertEqual(domains[3],[clamp(math.floor(x*16384+0.5),-16384,16384) for x in domains[0]])

    def test_avr_double_precision_is_rejected(self):
        compiler=shutil.which('avr-g++')
        if not compiler:self.skipTest('Optional AVR precision diagnostic requires avr-g++')
        probe=OUT/'precision.cpp';probe.write_text('#include "Lpx4HybridCore.h"\n')
        result=subprocess.run([compiler,'-mmcu=atmega328p','-std=gnu++11','-fsyntax-only',
            '-I'+str(SRC),'-DLPX4_FLOAT_SYNTHESIS=1','-DLPX4_ENABLE_ASM=0',
            '-DLPX4_ENABLE_PCM16=1',str(probe)],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requires at least IEEE binary64 precision',result.stderr)

    def test_invalid_numeric_mode_and_assembly_selection_fail_compile(self):
        probe=OUT/'probe.cpp';probe.write_text('#include "Lpx4HybridCore.h"\n')
        for flags,reason in ((['-DLPX4_FLOAT_SYNTHESIS=2'],'must be 0 or 1'),
            (['-DLPX4_FLOAT_SYNTHESIS=1','-DLPX4_ENABLE_ASM=1'],'requires C arithmetic')):
            result=subprocess.run(['g++','-std=c++11','-fsyntax-only','-I'+str(SRC),*flags,str(probe)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertIn(reason,result.stderr)

if __name__=='__main__':unittest.main()
