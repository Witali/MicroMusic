"""Prove compact error-guard removal preserves complete native API traces.

All fixtures are deterministic public test generators. Both compared backends
explicitly select C. The active source is never modified: private copies restore
or remove only the compact guard. Full16-configuration verification is a CLI
check; --quick selects the normal-CI smoke configuration. Needs g++ and Python's
standard library, without NumPy, AVR tools or a media corpus.
"""
from pathlib import Path
import argparse,ctypes as ct,hashlib,json,platform,random,shutil,struct,subprocess,sys,time

ACTIVE=Path(__file__).resolve().parents[1]
REPO=ACTIVE.parents[2]
sys.path[:0]=[str(ACTIVE/'tests'),str(ACTIVE/'tools')]
from test_sram512_profile import fixture
from test_speech_v9 import sparse_fixture,all_pairs
from speech_v9 import repack

MATRIX=[(version,memory,rom,batch) for version in (5,9) for memory in (0,1) for rom in (0,1) for batch in (0,1)]
SMOKE=[(9,1,1,1)]

def digest(data):return hashlib.sha256(data).hexdigest()

def guard_variants(source):
    """Fail closed if the reviewed compact branch/anchor has changed."""
    start=source.index('bool Lpx4HybridCore::decodeCode(int8_t& q){')
    end=source.index('\n#else\n int16_t decoded=0;',start)
    compact=source[start:end]
    anchor=' if(decoded < -32)decoded=-32;'
    check=' if(error_)return false;\n'
    if compact.count(anchor)!=1 or compact.count(check) not in (0,1):
        raise ValueError('Review the compact error invariant before updating this fixture')
    present=check in compact
    if present:
        if check+anchor not in compact:raise ValueError('Compact guard is no longer adjacent to clipping')
        without=source[:start]+compact.replace(check,'',1)+source[end:]
        with_check=source
    else:
        with_check=source[:start]+compact.replace(anchor,check+anchor,1)+source[end:]
        without=source
    assert with_check.replace(check+anchor,anchor,1)==without
    return with_check,without,present

HARNESS=r'''

#include "Lpx4HybridCore.h"
#include <stdint.h>
struct Input{const uint8_t* data;uint32_t available,position,calls;int16_t failure;};
static int16_t reader(void* p){Input& s=*static_cast<Input*>(p);++s.calls;if(s.position>=s.available)return s.failure;return s.data[s.position++];}
static uint32_t row(Lpx4HybridCore& d,Input& s,uint32_t* out,uint32_t at,uint32_t phase,bool got,uint32_t value){
 uint32_t* r=out+at*10;r[0]=phase;r[1]=got;r[2]=value;r[3]=d.error();r[4]=d.samples();r[5]=d.produced();r[6]=d.finished();r[7]=d.sampleRate();r[8]=s.calls;r[9]=s.position;return at+1;
}
static bool step(Lpx4HybridCore& d,uint8_t domain,uint32_t& value){
 int16_t signedOut=0x5aa5;uint8_t pwm=0xa5;bool ok;
 if(domain==0)ok=d.nextQ14(signedOut);else if(domain==1)ok=d.nextS16(signedOut);else ok=d.next(pwm);
 value=domain==2?pwm:static_cast<uint16_t>(signedOut);return ok;
}
extern "C" int trace_api(const uint8_t* data,uint16_t size,uint32_t available,int16_t failure,uint8_t mode,uint8_t domain,uint32_t budget,uint32_t* out,uint32_t capacity){
 Lpx4HybridCore d;Input s={data,available,0,0,failure};uint32_t at=0,value=0;
 at=row(d,s,out,at,0,false,0);
 if(mode==2||mode==5||mode==8){
  if(mode==5)s.available=1;
  bool ok=d.beginStream(reader,&s,size);at=row(d,s,out,at,3,ok,0);
  if(mode==8){for(uint32_t j=0;ok&&j<budget;j++){ok=step(d,domain,value);at=row(d,s,out,at,4,ok,value);}}
  else {ok=step(d,domain,value);at=row(d,s,out,at,4,ok,value);}
 }else if(mode==3||mode==7){
  bool ok=d.begin(data,size);at=row(d,s,out,at,3,ok,0);ok=step(d,domain,value);at=row(d,s,out,at,4,ok,value);
 }
 bool ok;
 if(mode==1||mode==3||mode==4)ok=d.beginStream(mode==4?0:reader,&s,size);
 else ok=d.begin(mode==6||mode==7?0:data,size);
 at=row(d,s,out,at,1,ok,0);
 uint8_t falseCalls=0;
 for(uint32_t j=0;j<budget&&falseCalls<3;j++){
  if(at>=capacity)return -1;
  bool got=step(d,domain,value);at=row(d,s,out,at,2,got,value);
  falseCalls=got?0:falseCalls+1;
 }
 return at;
}
'''

def streams(version):
 result=[]
 for profile in (4,6,15):
  for n in (1,19,20,39,40,79,80,81,159,160,319,320,321,641,64000):
   old=sparse_fixture(n)[0] if profile==15 else fixture(profile,n,145,'changing',True)
   blob=repack(old)[0] if version==9 else old
   result.append((profile,n,blob))
 return result

class GuardAudit:
    def __init__(self,output,compiler='g++'):
        self.output=Path(output).resolve();self.compiler=compiler
        if not self.output.is_relative_to((REPO/'build').resolve()):raise ValueError('Use ignored repository build storage')
        self.counts=dict(trace_comparisons=0,api_rows_compared=0,valid=0,malformed_or_mutated=0,callback_eof=0,source_switch=0)

    def command(self,*args):
        result=subprocess.run(args,capture_output=True)
        if result.returncode:
            (self.output/'compiler-error.log').write_bytes(result.stdout+result.stderr)
            raise RuntimeError('Native compiler failed; inspect compiler-error.log in the chosen build directory')
        return result.stdout

    def prepare(self):
        self.output.mkdir(parents=True,exist_ok=True)
        if any(self.output.iterdir()):raise ValueError('Use a fresh output directory')
        source=(ACTIVE/'src/Lpx4HybridCore.cpp').read_text(encoding='utf-8')
        with_check,without,self.current_guard_present=guard_variants(source)
        for name,text in (('original',with_check),('removed',without)):
            shutil.copytree(ACTIVE/'src',self.output/name)
            (self.output/name/'Lpx4HybridCore.cpp').write_text(text,encoding='utf-8',newline='\n')
        (self.output/'trace.cpp').write_text(HARNESS,encoding='ascii',newline='\n')
        self.variants=dict(with_check_sha256=digest(with_check.encode()),without_check_sha256=digest(without.encode()))
        dependencies=[Path(__file__),ACTIVE/'tests/test_sram512_profile.py',ACTIVE/'tests/test_speech_v9.py',ACTIVE/'tools/speech_v9.py',
                      *sorted(p for p in (ACTIVE/'src').rglob('*') if p.is_file() and '__pycache__' not in p.parts)]
        self.source_sha256={p.relative_to(REPO).as_posix():digest(p.read_bytes().replace(b'\r\n',b'\n')) for p in dependencies}
        pre=[]
        for name in ('original','removed'):
            pre.append(self.command(self.compiler,'-E','-P','-std=c++11','-DLPX4_ENABLE_ASM=0','-DLPX4_COMPACT_ONLY=0',
                    '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1','-I'+str(self.output/name),str(self.output/name/'Lpx4HybridCore.cpp')))
        if pre[0]!=pre[1]:raise AssertionError('Noncompact preprocessed source changed')


    def library(self,name,version,memory,rom,batch):
     p=self.output/('%s-v%d-m%d-r%d-b%d.so'%(name,version,memory,rom,batch))
     flags=['-O2','-std=c++11','-shared','-fPIC','-DLPX4_ENABLE_ASM=0',
      '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1','-DLPX4_COMPACT_ONLY=1',
      '-DLPX4_ENABLE_INPUT_CALLBACK=1',f'-DLPX4_COMPACT_VERSION={version}',
      '-DLPX4_ENABLE_SPARSE80=1',f'-DLPX4_MEMORY_PROFILE={memory}',f'-DLPX4_ROM_POINTER={rom}',f'-DLPX4_BATCHED_REMAINING={batch}']
     self.command(self.compiler,*flags,'-I'+str(self.output/name),str(self.output/name/'Lpx4HybridCore.cpp'),str(self.output/'trace.cpp'),'-o',str(p))
     lib=ct.CDLL(str(p));f=lib.trace_api
     f.argtypes=[ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint32,ct.c_int16,ct.c_uint8,ct.c_uint8,ct.c_uint32,ct.POINTER(ct.c_uint32),ct.c_uint32]
     f.restype=ct.c_int
     return lib

    def compare(self,pair,blob,*,available=None,failure=-1,mode=0,domain=0,category='valid',long=False):
     size=len(blob);available=size if available is None else available
     n=int.from_bytes(blob[5:7] if blob[:2]==b'L9' else blob[8:12],'little')
     budget=(n+8) if long else min(n+8,2056);budget=max(8,budget)
     capacity=2*budget+16;data=(ct.c_uint8*max(1,size))(*blob)
     output=[]
     for lib in pair:
      buf=(ct.c_uint32*(capacity*10))();got=lib.trace_api(data,size,available,failure,mode,domain,budget,buf,capacity)
      assert 0<=got<=capacity
      output.append(bytes(buf)[:got*40])
     assert output[0]==output[1],dict(category=category,size=size,available=available,failure=failure,mode=mode,domain=domain)
     self.counts['trace_comparisons']+=1;self.counts['api_rows_compared']+=len(output[0])//40;self.counts[category]+=1

    def exercise(self,pair,version):
     valid=streams(version)
     for profile,n,blob in valid:
      for domain in (0,1,2):
       for mode in (0,1):self.compare(pair,blob,domain=domain,mode=mode,long=n==64000)
      if n in (1,81,321,641):
       for domain in (0,1,2):
        for mode in (2,3,4,5,6,7,8):self.compare(pair,blob,domain=domain,mode=mode,available=len(blob)//2 if mode==8 else None,category='source_switch')
     for profile in (4,6,15):
      blob=next(b for p,n,b in valid if p==profile and n==321)
      malformed=[blob[:i] for i in range(len(blob))]+[blob+b'\0']
      start=13 if version==9 else 22;profile_at=2 if version==9 else 5
      for value in (0,7,8,12,14,64,68,70,143,255):
       b=bytearray(blob);b[profile_at]=value;malformed.append(bytes(b))
      for at,width,value in ((0,1,0),(3 if version==9 else 6,2,16000),
       (5 if version==9 else 8,2 if version==9 else 4,0),
       (5 if version==9 else 8,2 if version==9 else 4,64001),
       (5 if version==9 else 8,2 if version==9 else 4,65535),
       (7 if version==9 else 12,2,16385),(9 if version==9 else 14,2,11470)):
       b=bytearray(blob);b[at:at+width]=value.to_bytes(width,'little');malformed.append(bytes(b))
      b=bytearray(blob+b'\0');struct.pack_into('<H',b,11 if version==9 else 20,len(b)-start);malformed.append(bytes(b))
      b=bytearray(blob);b[-1]|=128;malformed.append(bytes(b))
      b=bytearray(blob);b[start]&=~1;malformed.append(bytes(b))
      rng=random.Random(20261110+profile+version)
      for _ in range(50):
       b=bytearray(blob);at=rng.randrange(start,len(b));b[at]^=1<<rng.randrange(8);malformed.append(bytes(b))
      for b in malformed:
       for domain in (0,1,2):self.compare(pair,b,domain=domain,category='malformed_or_mutated')
      for available in range(len(blob)+1):
       for failure in (-1,256):self.compare(pair,blob,available=available,failure=failure,mode=1,category='callback_eof')
      for available in sorted(set((0,1,start-1,start,len(blob)//2,len(blob)-1,len(blob)))):
       for failure in (-32768,0,255,32767):
        for domain in (0,1,2):self.compare(pair,blob,available=available,failure=failure,mode=1,domain=domain,category='callback_eof')
     if version==9:
      blob=repack(bytes(all_pairs()))[0]
      for domain in (0,1,2):self.compare(pair,blob,domain=domain,long=True)
      good=repack(fixture(6,40,18,'static',False))[0]
      for high in range(25,32):
       for low in range(16):
        b=bytearray(good)
        for bit in range(4):
         at=47+bit;mask=1<<(at&7);b[13+(at>>3)]=(b[13+(at>>3)]&~mask)|(((low>>bit)&1)<<(at&7))
        for bit in range(5):
         at=47+4+bit;mask=1<<(at&7);b[13+(at>>3)]=(b[13+(at>>3)]&~mask)|(((high>>bit)&1)<<(at&7))
        self.compare(pair,bytes(b),category='malformed_or_mutated')

    def run(self,configurations=None):
        started=time.perf_counter();configurations=MATRIX if configurations is None else list(configurations)
        if not configurations or any(c not in MATRIX for c in configurations):raise ValueError('Unsupported verification configuration')
        self.prepare();matrix=[]
        compiler=self.command(self.compiler,'--version').decode(errors='replace').splitlines()[0]
        for version,memory,rom,batch in configurations:
            pair=[self.library(name,version,memory,rom,batch) for name in ('original','removed')]
            before=self.counts['trace_comparisons'];self.exercise(pair,version)
            item=dict(version=version,memory=memory,rom=rom,batch=batch,trace_comparisons=self.counts['trace_comparisons']-before,exact=True)
            matrix.append(item);print(json.dumps(item),flush=True)
        report=dict(schema='lpx-compact-error-guard-v1',source_hash_encoding='UTF-8, LF',source_sha256=self.source_sha256,
            current_guard_present=self.current_guard_present,variant_sha256=self.variants,
            current_source_sha256=self.source_sha256['Codecs/LPX/01_ACTIVE_Q0_CODEC/src/Lpx4HybridCore.cpp'],
            explicit_c_backend=True,noncompact_preprocessed_exact=True,all_api_traces_exact=True,
            matrix=matrix,counts=self.counts,compiler=compiler,python=platform.python_version(),seconds=time.perf_counter()-started,
            trace_fields=['phase','return','output_including_false_call','error','samples','produced','finished','sample_rate','callback_calls','callback_position'],
            domains=['Q14','PCM16','PWM8'],fixtures='Public deterministic fixture generators and fixed-seed payload mutations; no media corpus',
            scope='Native API equivalence only. Requires non-reentrant exclusive access to a decoder instance; no AVR speed/size or physical-board claim.')
        report['full_matrix']=configurations==MATRIX
        (self.output/'summary.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
        return report



def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--cxx',default='g++')
    parser.add_argument('--quick',action='store_true',help='One representative configuration; full matrix is the default')
    args=parser.parse_args();report=GuardAudit(args.output,args.cxx).run(SMOKE if args.quick else None)
    print(json.dumps(dict(complete=True,full_matrix=report['full_matrix'],**report['counts'],seconds=report['seconds'])))

if __name__=='__main__':main()
