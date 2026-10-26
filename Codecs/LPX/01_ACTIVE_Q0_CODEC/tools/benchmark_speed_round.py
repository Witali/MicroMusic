"""Frozen golden-stream AVR benchmark for iterative decoder speed rounds.

Independent process shards use separate reports; each complete image retains
its source/settings fingerprint. Resume only reuses a verified terminal image,
never a live process or merely a lock file. All generated binaries stay in build/.
"""
import argparse,hashlib,json
from pathlib import Path
from batch_decoder import BatchSession
from profile_avr import run as profile,ROOT,HARNESS

def sha(data):return hashlib.sha256(data).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')

def run(manifest,base,output,avr_bin,runner,lib=None,wsl=None,shard=0,shards=1):
    if not 0<=shard<shards:raise ValueError('Invalid shard')
    manifest,base,output=map(Path,(manifest,base,output));output.mkdir(parents=True,exist_ok=True)
    points=json.loads(manifest.read_text(encoding='utf-8'));unique={}
    for p in points:
        key=p['stream_sha256']
        if key in unique:
            for field in ('samples','pcm16_sha256','pwm_sha256'):assert unique[key][field]==p[field]
        unique[key]=p
    source_hashes={p.name:sha(p.read_bytes()) for p in sorted((ROOT/'src').iterdir()) if p.is_file()}
    source_hashes.update(harness=sha((HARNESS/'profile.cpp').read_bytes()),runner=sha((HARNESS/'sim_profile.c').read_bytes()))
    settings={'enable_asm':True,'queue':512,'prefill':384,'irq_load':0,'dot_unroll':9,'v3_features':24}
    fingerprint=sha(json.dumps([source_hashes,settings,sha(manifest.read_bytes())],sort_keys=True).encode())
    result={'source_sha256':source_hashes,'settings':settings,'fingerprint':fingerprint,
        'manifest_sha256':sha(manifest.read_bytes()),'golden_points':len(points),'golden_unique':len(unique),
        'shard':shard,'shards':shards,'images':{},'physical_hardware_measured':False}
    rows=[p for i,p in enumerate(unique.values()) if i%shards==shard]
    report_path=output/f'part-{shard}.json'
    with BatchSession('batch',v3_features=24) as decoder:
        for p in rows:
            key=p['stream_sha256'];path=base/p['path'];blob=path.read_bytes()
            assert sha(blob)==key
            pcm=decoder.decode_one_s16(blob,p['samples']);pwm=decoder.decode_one(blob,p['samples'])
            assert pcm is not None and pwm is not None
            assert sha(pcm.astype('<i2').tobytes())==p['pcm16_sha256'] and sha(pwm.tobytes())==p['pwm_sha256']
            folder=output/key;cache=folder/'round.json';measurement=None
            if cache.exists():
                old=json.loads(cache.read_text(encoding='utf-8'));r=old.get('measurement',{})
                if old.get('fingerprint')==fingerprint and r.get('done') and r.get('input_sha256')==key:
                    elf,hexfile=folder/'profile.elf',folder/'profile.hex'
                    if elf.exists() and hexfile.exists() and sha(elf.read_bytes())==r['elf_sha256'] and sha(hexfile.read_bytes())==r['hex_sha256']:
                        measurement=r
            if measurement is None:
                r=profile(path,folder,avr_bin,runner,lib,wsl,**settings)
                measurement={k:v for k,v in r.items() if k!='occupancy_trace'}
                measurement['raw_report_sha256']=sha((folder/'report.json').read_bytes())
                save(cache,{'fingerprint':fingerprint,'measurement':measurement})
            assert measurement['pwm_sha256']==p['pwm_sha256'] and measurement['pwm_native_exact']
            assert measurement['played']==measurement['produced']==p['samples'] and not measurement['decoder_error']
            assert measurement['flash_bytes']<=32768 and measurement['stack_margin_bytes']>0
            assert measurement['underruns']==0
            result['images'][key]=measurement;save(report_path,result)
            print(shard,len(result['images']),len(rows),key,round(measurement['mean_decode_wall_cycles'],3),flush=True)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('manifest',type=Path);ap.add_argument('output',type=Path)
    ap.add_argument('--base',type=Path,default=Path.cwd());ap.add_argument('--avr-bin',type=Path,required=True)
    ap.add_argument('--sim-runner',type=Path,required=True);ap.add_argument('--sim-lib-dir',type=Path);ap.add_argument('--wsl')
    ap.add_argument('--shard',type=int,default=0);ap.add_argument('--shards',type=int,default=1)
    a=ap.parse_args();run(a.manifest,a.base,a.output,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl,a.shard,a.shards)
