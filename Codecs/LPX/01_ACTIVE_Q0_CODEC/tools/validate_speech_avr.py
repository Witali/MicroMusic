"""Complete active-IRQ AVR measurements for local LPX speech comparisons."""
import argparse, json, struct, subprocess
from pathlib import Path
import numpy as np
from profile_avr import run as profile, ROOT, HARNESS
from benchmark_standards import sha, save
from batch_decoder import BatchSession
from speech_v4 import decode_model


def repeated(blob):
    n=int.from_bytes(blob[8:12],'little')
    if n%320 or n>32000:raise ValueError('Repeat requires complete packets, at most four seconds')
    header=bytearray(blob[:20]);struct.pack_into('<I',header,8,n*2)
    if blob[4]==4:return bytes(header)+blob[20:]*2
    from lpx4 import decode, encode
    from compact_format import pack
    frames,blocks,q=decode(blob);header[:6]=b'L3AV\x01\x03'
    result=encode({'raw':bytes(header),'frames':frames*2,'blocks':blocks*2},fast=True)[0]
    return min((result,pack(result,24)[0]),key=lambda b:(len(b),b))


def run(comparison,output,avr_bin,runner,lib,wsl,profiles=(4,6,8)):
    comparison,output=Path(comparison),Path(output);output.mkdir(parents=True,exist_ok=True)
    sources={p.name:sha(p.read_bytes()) for p in (ROOT/'src').iterdir() if p.is_file()}
    compiler=Path(avr_bin)/'avr-g++.exe' if Path(avr_bin,'avr-g++.exe').exists() else Path(avr_bin)/'avr-g++'
    cc1=Path(subprocess.check_output([str(compiler),'-print-prog-name=cc1plus'],text=True).strip())
    dependencies={p.name:sha(p.read_bytes()) for p in (HARNESS/'profile.cpp',HARNESS/'sim_profile.c',
        Path(runner),compiler,cc1,Path(__file__),ROOT/'tools/profile_avr.py')}
    for p in Path(lib).glob('*.so*'):
        try:dependencies['sim-library-'+p.name]=sha(p.read_bytes())
        except OSError:
            # WSL symlinks may not be readable from Win32; the corresponding
            # regular versioned library files in this directory are hashed.
            dependencies['sim-library-'+p.name]='WSL symlink; regular targets hashed separately'
    settings={'queue':512,'prefill':384,'dot_unroll':9,'v3_features':24}
    report={'source_sha256':sources,'cases':{},'stress':{},'partial_tails':{},
            'measurement_dependencies':dependencies,'settings':settings,'physical_hardware_measured':False}
    def measure(path,key,assembly=True,load=0,speech=True):
        folder=output/key;source=path.read_bytes()
        fingerprint=sha(json.dumps([sources,dependencies,settings,sha(source),assembly,load,speech],sort_keys=True).encode())
        cache=folder/'complete.json'
        if cache.exists():
            old=json.loads(cache.read_text(encoding='utf-8'))
            if old.get('fingerprint')==fingerprint:
                r=old['measurement']
                if sha((folder/'profile.elf').read_bytes())==r['elf_sha256'] and sha((folder/'profile.hex').read_bytes())==r['hex_sha256']:
                    return r
        r=profile(path,folder,avr_bin,runner,lib,wsl,enable_asm=assembly,irq_load=load,
                  **settings,speech=speech)
        r['first_output_tick_cycles']=r['occupancy_trace'][0]['cycle']
        r['first_output_from_reset_ms']=r['first_output_tick_cycles']/16000
        r['stack_high_water_bytes_after_ready']=2304-r['minimum_stack_pointer']
        r['flash_excluding_stream_bytes']=r['flash_bytes']-r['input_bytes']
        r={k:v for k,v in r.items() if k!='occupancy_trace'}
        assert r['played']==r['produced']==r['input_samples'] and not r['decoder_error']
        assert r['pwm_native_exact'] and r['stack_margin_bytes']>0 and r['flash_bytes']<=32768
        save(cache,{'fingerprint':fingerprint,'measurement':r})
        print(key,round(r['mean_decode_wall_cycles'],3),r['underruns'],'underruns',flush=True)
        return r
    for folder in sorted(comparison.glob('case-*')):
        row={}
        for p in profiles:
            path=folder/f'lpx{p}.l4hy';row[str(p)]=measure(path,f'{folder.name}-{p}')
        # Quantify enabling the additional parser for legacy streams as well.
        if 8 in profiles:
            row['8_without_speech']=measure(folder/'lpx8.l4hy',f'{folder.name}-8-original',speech=False)
            assert row['8']['pwm_sha256']==row['8_without_speech']['pwm_sha256']
        report['cases'][folder.name]=row;save(output/'verification.json',report)
    for p in profiles:
        heaviest=max(report['cases'],key=lambda k:report['cases'][k][str(p)]['mean_decode_wall_cycles'])
        blob=repeated((comparison/heaviest/f'lpx{p}.l4hy').read_bytes())
        path=output/f'repeat-{p}.l4hy';path.write_bytes(blob)
        with BatchSession('batch',v3_features=24,speech=True) as decoder:
            pcm=decoder.decode_one_s16(blob,64000)
            if p in (4,6):np.testing.assert_array_equal(pcm,decode_model(blob))
            else:
                from q0_model import decode_pcm16
                np.testing.assert_array_equal(pcm,decode_pcm16(blob))
        row={'source_case':heaviest,'continuous_state_samples':64000}
        for name,assembly,load in (('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)):
            row[name]=measure(path,f'repeat-{p}-{name}',assembly,load)
        report['stress'][str(p)]=row;save(output/'verification.json',report)
    from test_speech_v4 import fixture
    for p in (4,6):
        for n in (1,19,161,319,321):
            path=output/f'partial-{p}-{n}.l4hy';path.write_bytes(fixture(p,n))
            report['partial_tails'][f'{p}-{n}']=measure(path,f'partial-{p}-{n}')
    save(output/'verification.json',report)
    return report


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('comparison',type=Path);ap.add_argument('output',type=Path)
    for key in ('avr-bin','runner','lib','wsl'):ap.add_argument('--'+key,required=True)
    ap.add_argument('--profiles',type=int,choices=(4,6,8),nargs='+',default=(4,6,8))
    a=ap.parse_args();run(a.comparison,a.output,a.avr_bin,a.runner,a.lib,a.wsl,a.profiles)
