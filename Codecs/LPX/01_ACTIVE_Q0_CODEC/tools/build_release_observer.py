"""Compile the external player observer; never link its metadata into AVR code."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
from output_paths import protect_outputs
from profile_avr import linux_path
SOURCE=Path(__file__).resolve().parents[2]/'validation/atmega328p/sim_player.c'
REPOSITORY=Path(__file__).resolve().parents[4]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build(output,include,lib,*,wsl=None,compiler='gcc'):
    folder=Path(output).resolve();include=Path(include).resolve();lib=Path(lib).resolve()
    if not folder.is_relative_to((REPOSITORY/'build').resolve()) or folder==(REPOSITORY/'build').resolve():raise ValueError('Observer artifacts must stay in ignored build storage')
    names=['sim_player','observer-build.json','compile.stdout.log','compile.stderr.log'];targets=[folder/n for n in names]
    for p in targets:
        if not p.resolve().is_relative_to((REPOSITORY/'build').resolve()) or p.is_symlink() or (p.exists() and p.stat().st_nlink>1):raise ValueError('Observer output alias')
    def readable_file(p):
        try:return p.is_file()
        except OSError:return False # WSL symlink; physical shared objects are hashed.
    headers=[p for p in include.rglob('*') if readable_file(p)]
    headers += [p for p in (include.parent/'gelf.h',include.parent/'libelf.h') if readable_file(p)]
    libraries=[p for p in lib.glob('libsimavr*') if readable_file(p)]+[p for p in lib.glob('libelf*') if readable_file(p)]
    if not headers or not libraries:raise ValueError('Observer headers/libraries missing')
    inputs=[SOURCE,Path(__file__),*headers,*libraries];protect_outputs(inputs,targets);folder.mkdir(parents=True,exist_ok=True)
    def path(p):return linux_path(p) if wsl else str(p)
    prefix=['wsl','-d',wsl,'--'] if wsl else []
    version=subprocess.check_output([*prefix,compiler,'--version'],text=True).splitlines()[0]
    hashes={str(p):digest(p) for p in inputs};flags=['-O2','-std=c11','-Wall','-Wextra','-Werror','-I'+path(include),'-I'+path(include.parent),path(SOURCE),'-L'+path(lib),'-lsimavr','-lelf','-lz','-lzstd','-o',path(folder/'sim_player')]
    identity=hashlib.sha256(json.dumps([hashes,version,flags],sort_keys=True,separators=(',',':')).encode()).hexdigest();cache=folder/'observer-build.json'
    if cache.is_file() and (folder/'sim_player').is_file():
        old=json.loads(cache.read_text())
        if old.get('fingerprint')==identity and old.get('binary_sha256')==digest(folder/'sim_player'):return folder/'sim_player'
    result=subprocess.run([*prefix,compiler,*flags],capture_output=True)
    (folder/'compile.stdout.log').write_bytes(result.stdout);(folder/'compile.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('Observer compilation failed; see ignored compile.stderr.log')
    if {str(p):digest(p) for p in inputs}!=hashes:raise ValueError('Observer sources changed during compilation')
    cache.write_text(json.dumps(dict(fingerprint=identity,binary_sha256=digest(folder/'sim_player'),source_sha256=hashes,compiler=version,compiler_options=flags),indent=2)+'\n',encoding='utf-8',newline='\n')
    return folder/'sim_player'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--include',required=True,type=Path);p.add_argument('--lib',required=True,type=Path);p.add_argument('--wsl');p.add_argument('--compiler',default='gcc');a=p.parse_args();build(a.output,a.include,a.lib,wsl=a.wsl,compiler=a.compiler);print('Observer compiled or verified from cache')
if __name__=='__main__':main()
