"""Full active-IRQ AVR admission of completed legacy profile results.

Cache identity covers actual firmware sources, tools, headers and runner.
No physical-board claim; C fallback value equality and timing are separate.
"""
import argparse,json,os,struct,subprocess,time
from pathlib import Path
import numpy as np
from batch_decoder import BatchSession
from benchmark_standards import save,sha
from profile_avr import ROOT,HARNESS,run as profile
from lpx4 import decode,encode
from compact_format import pack
from q0_model import decode_pcm16
from standard_metrics import pwm_duties

SETTINGS={'queue':512,'prefill':384,'dot_unroll':9,'v3_features':24}
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(path):return sha(Path(path).read_bytes())
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':')).encode()

def environment(avr_bin,runner,lib,wsl):
    avr_bin,runner=Path(avr_bin),Path(runner);suffix='.exe' if os.name=='nt' else ''
    compiler=avr_bin/('avr-g++'+suffix)
    files=[HARNESS/'profile.cpp',HARNESS/'sim_profile.c',ROOT/'tools/profile_avr.py',
           ROOT/'tools/batch_decoder.py',Path(__file__),compiler,runner]
    files.append(Path(subprocess.check_output([str(compiler),'-print-prog-name=cc1plus'],text=True).strip()))
    for name in ('avr-as','avr-ld','avr-size','avr-objcopy'):files.append(avr_bin/(name+suffix))
    for name in ('libgcc.a','libc.a','crtatmega328p.o'):
        path=Path(subprocess.check_output([str(compiler),'-mmcu=atmega328p','-print-file-name='+name],text=True).strip())
        if not path.is_file():raise ValueError('Toolchain runtime input not found')
        files.append(path)
    headers=sorted((avr_bin.parent/'avr/include').rglob('*.h'))
    if not headers:raise ValueError('AVR device/library headers were not found')
    dependencies={p.name:digest(p) for p in files}
    dependencies['device_headers_sha256']=sha(b''.join(str(p.relative_to(avr_bin.parent)).encode()+p.read_bytes() for p in headers))
    dependencies['device_header_count']=len(headers)
    for p in sorted(Path(lib).glob('*.so*')):
        try:dependencies['sim-library-'+p.name]=digest(p)
        except OSError:dependencies['sim-library-'+p.name]='WSL symlink; regular target is hashed separately'
    return {'sources':{p.name:digest(p) for p in sorted((ROOT/'src').iterdir()) if p.is_file()},
            'dependencies':dependencies,'settings':SETTINGS,'wsl':wsl,
            'compiler':subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0]}

def measure(path,folder,env,avr_bin,runner,lib,wsl,assembly=True,irq=0,expected_pwm=None):
    path,folder=Path(path),Path(folder);blob=path.read_bytes();n=int.from_bytes(blob[8:12],'little')
    fingerprint=sha(canonical([env,sha(blob),assembly,irq]));record=None;cache=folder/'complete.json'
    if cache.exists():
        prior=load(cache);candidate=prior.get('measurement',{})
        if prior.get('fingerprint')==fingerprint and prior.get('environment')==env and prior.get('measurement_sha256')==sha(canonical(candidate)):
            if all((folder/name).is_file() and digest(folder/name)==candidate.get(key) for name,key in
                   (('profile.elf','elf_sha256'),('profile.hex','hex_sha256'),('valid.pcm8','pwm_sha256'))):record=candidate
    if record is None:
        record=profile(path,folder,avr_bin,runner,lib,wsl,enable_asm=assembly,irq_load=irq,**SETTINGS)
        record['first_output_from_reset_ms']=record['occupancy_trace'][0]['cycle']/16000
        record['stack_high_water_bytes_after_ready']=2304-record['minimum_stack_pointer']
        record['flash_excluding_stream_bytes']=record['flash_bytes']-record['input_bytes']
        record={k:v for k,v in record.items() if k!='occupancy_trace'}
        save(cache,{'fingerprint':fingerprint,'environment':env,'measurement_sha256':sha(canonical(record)),'measurement':record})
    if not record['done'] or record['decoder_error'] or not record['pwm_native_exact']:raise AssertionError('Incomplete AVR output')
    if not record['input_samples']==record['played']==record['produced']==record['decode_calls']==n:raise AssertionError('AVR sample mismatch')
    if record['timer_ticks']!=n+record['underruns'] or record['input_sha256']!=sha(blob):raise AssertionError('AVR stream/timer mismatch')
    if expected_pwm is not None and record['pwm_sha256']!=expected_pwm:raise AssertionError('Full expected PWM mismatch')
    if record['flash_bytes']>32768 or record['stack_margin_bytes']<=0:raise AssertionError('AVR memory limit failed')
    for field,name in (('core_sha256','Lpx4HybridCore.cpp'),('core_header_sha256','Lpx4HybridCore.h'),('math_header_sha256','Lpx4Math.h')):
        if record[field]!=env['sources'][name]:raise AssertionError('AVR source changed')
    expected={'cpu_hz':16000000,'audio_hz':8000,'queue_bytes':512,'prefill_samples':384,'dot_unroll':9,
        'v3_compiled_features':24,'speech_compiled':False,'speech_compact_compiled':False,
        'arithmetic_backend':'avr5-asm' if assembly else 'c','extra_irq_cycles':irq}
    if not all(record.get(k)==v for k,v in expected.items()):raise AssertionError('AVR options changed')
    return record

def run(inputs,results,output,avr_bin,runner,lib,wsl,watch=False):
    inputs,results,output=Path(inputs),Path(results),Path(output);manifest=load(inputs)
    env=environment(avr_bin,runner,lib,wsl);output.mkdir(parents=True,exist_ok=True)
    target=output/'verification.json'
    report=load(target) if target.exists() else {'cases':{},'images':{},'environment':env,'physical_hardware_measured':False}
    if report['environment']!=env:raise ValueError('AVR environment changed; use a separate output tree')
    with BatchSession('batch',v3_features=24) as decoder:
        while True:
            for c in manifest['cases']:
                completed=results/c['id']/'complete.json'
                if not completed.exists():continue
                data=load(completed)
                if report['cases'].get(c['id'],{}).get('quality_fingerprint')==data['fingerprint']:continue
                points=[]
                for row in data['rates']:
                    for stage in ('baseline','selected'):
                        meta=row[stage];path=results/c['id']/str(row['ceiling_bps'])/(stage+'.l4hy');blob=path.read_bytes()
                        if sha(blob)!=meta['stream_sha256'] or len(blob)>row['full_file_cap_bytes']:raise ValueError('Selected stream or cap changed')
                        pcm=decoder.decode_one_s16(blob,32000)
                        if pcm is None or sha(pcm.astype('<i2').tobytes())!=meta['pcm16_sha256'] or not np.array_equal(pcm,decode_pcm16(blob)):
                            raise AssertionError('Selected native/model output changed')
                        if sha(pwm_duties(pcm).tobytes())!=meta['pwm_sha256']:raise AssertionError('Selected PWM changed')
                        digest_key=meta['stream_sha256']
                        if digest_key not in report['images']:
                            record=measure(path,output/'images'/digest_key,env,avr_bin,runner,lib,wsl,expected_pwm=meta['pwm_sha256'])
                            if record['underruns']:raise ValueError('ASM admission failed; retain/reselect rollback before final delivery')
                            report['images'][digest_key]=record
                        record=report['images'][digest_key]
                        points.append({'ceiling_bps':row['ceiling_bps'],'stage':stage,'stream_sha256':digest_key,
                            'mean_decode_wall_cycles':record['mean_decode_wall_cycles'],'underruns':record['underruns'],
                            'flash_bytes':record['flash_bytes'],'static_sram_bytes':record['static_sram_bytes'],'avr_admitted':record['underruns']==0})
                report['cases'][c['id']]={'quality_fingerprint':data['fingerprint'],'points':points};save(target,report)
                print(c['id'],'AVR complete',len(report['cases']),'of',len(manifest['cases']),'unique images',len(report['images']),flush=True)
            if len(report['cases'])==len(manifest['cases']) or not watch:break
            time.sleep(5)
    return report

def stress(results,verification,output,avr_bin,runner,lib,wsl):
    results,output=Path(results),Path(output);admission=load(verification);env=environment(avr_bin,runner,lib,wsl)
    if admission['environment']!=env:raise ValueError('AVR environment differs from admission')
    report={'environment':env,'profiles':{},'physical_hardware_measured':False}
    with BatchSession('batch',v3_features=24) as decoder:
        for rate in (8000,12000,16000):
            eligible=[(case,p) for case,c in admission['cases'].items() for p in c['points'] if p['ceiling_bps']==rate and p['stage']=='selected']
            if len(eligible)!=27:raise ValueError('Stress requires the complete27-case admission')
            case,p=max(eligible,key=lambda pair:pair[1]['mean_decode_wall_cycles'])
            source=results/case/str(rate)/'selected.l4hy';blob=source.read_bytes()
            if sha(blob)!=p['stream_sha256']:raise ValueError('Stress source changed')
            frames,blocks,q=decode(blob);raw=bytearray(blob[:20]);raw[:6]=b'L3AV\x01\x03';struct.pack_into('<I',raw,8,len(q)*2)
            repeated=encode({'raw':bytes(raw),'frames':frames*2,'blocks':blocks*2},fast=True)[0]
            smaller=pack(repeated,24)[0]
            if len(smaller)<len(repeated):repeated=smaller
            pcm=decoder.decode_one_s16(repeated,64000)
            if pcm is None or not np.array_equal(pcm,decode_pcm16(repeated)):raise AssertionError('Continuous native/model mismatch')
            path=output/str(rate)/'repeat.l4hy';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(repeated)
            row={'source_case':case,'source_stream_sha256':p['stream_sha256'],'repeat_stream_sha256':sha(repeated),
                'samples':64000,'continuous_state':True,'quality_reference':False,'images':{}}
            for name,assembly,irq in (('normal',True,0),('extra_irq100',True,100),('c_fallback',False,0)):
                measured=measure(path,path.parent/name,env,avr_bin,runner,lib,wsl,assembly,irq,sha(pwm_duties(pcm).tobytes()))
                if assembly and measured['underruns']:raise ValueError('Long ASM timing admission failed')
                row['images'][name]=measured
            report['profiles'][str(rate)]=row;save(output/'verification.json',report)
            print(rate,'continuous controls complete',flush=True)
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=('run','stress'))
    ap.add_argument('inputs',type=Path);ap.add_argument('results',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--avr-bin',type=Path,required=True);ap.add_argument('--runner',type=Path,required=True);ap.add_argument('--lib',type=Path,required=True);ap.add_argument('--wsl',default='Ubuntu');ap.add_argument('--watch',action='store_true')
    a=ap.parse_args()
    if a.mode=='run':run(a.inputs,a.results,a.output,a.avr_bin,a.runner,a.lib,a.wsl,a.watch)
    else:stress(a.results,a.inputs,a.output,a.avr_bin,a.runner,a.lib,a.wsl)
