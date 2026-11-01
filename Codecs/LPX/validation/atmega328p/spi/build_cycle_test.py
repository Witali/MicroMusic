"""Build and execute the isolated SPI timing test against pinned simavr1.6."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import traceback

from patch_simavr_spi import patched,UPSTREAM_SHA256

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sha=lambda raw:hashlib.sha256(raw).hexdigest()


def save(path,value):path.write_bytes(json.dumps(value,indent=2,allow_nan=False).encode()+b'\n')


def linux(path):
    path=path.resolve().as_posix()
    if len(path)<3 or path[1:3]!=':/':raise ValueError('Expected a mapped drive path')
    return '/mnt/'+path[0].lower()+'/'+path[3:]


def physical(path):
    try:return path.is_file()
    except OSError:return False


def build(args):
    if args.output.exists() or not args.output.is_relative_to(ROOT/'build'):
        raise ValueError('Use a fresh task build folder')
    args.output.mkdir(parents=True)
    save(args.output/'attempt-private.json',dict(status='running',test='SPI eight clock divisors',new_player_images=0))
    prefix=['wsl','-d',args.wsl,'--'] if args.wsl else []
    path=linux if args.wsl else str
    original=args.upstream.read_bytes()
    if sha(original)!=UPSTREAM_SHA256:raise ValueError('Wrong upstream SPI implementation')
    source=args.output/'avr_spi-clocked.c';source.write_bytes(patched(original))
    model=args.model_root/'w25q128_readonly.c'
    model_header=args.model_root/'w25q128_readonly.h'
    libraries=[p for p in args.lib.glob('libsimavr*') if physical(p)]+[p for p in args.lib.glob('libelf*') if physical(p)]
    headers=[p for p in args.include.rglob('*') if physical(p)]
    headers += [p for p in (args.include.parent/'gelf.h',args.include.parent/'libelf.h') if physical(p)]
    inputs=[Path(__file__),HERE/'patch_simavr_spi.py',HERE/'simavr_spi_clock.h',HERE/'test_spi_cycles.c',args.upstream,source,model,model_header,*headers,*libraries]
    pins={str(p):sha(p.read_bytes()) for p in inputs}
    version=subprocess.check_output([*prefix,'gcc','--version'],text=True).splitlines()[0]
    common=['-O2','-std=c11','-Wall','-Wextra','-Werror','-I'+path(args.include),'-I'+path(args.include.parent),'-I'+path(args.model_root)]
    spi_object=args.output/'avr_spi-clocked.o'
    compile_spi=[*prefix,'gcc',*common,'-Wno-unused-parameter','-c',path(source),'-o',path(spi_object)]
    binary=args.output/'test_spi_cycles'
    compile_test=[*prefix,'gcc',*common,path(HERE/'test_spi_cycles.c'),path(model),path(spi_object),
        '-L'+path(args.lib),'-lsimavr','-lelf','-lz','-lzstd','-o',path(binary)]
    for name,command in (('module',compile_spi),('test',compile_test)):
        result=subprocess.run(command,capture_output=True)
        (args.output/(name+'-compile.stdout.log')).write_bytes(result.stdout)
        (args.output/(name+'-compile.stderr.log')).write_bytes(result.stderr)
        if result.returncode:raise RuntimeError('Host '+name+' compilation failed')
    result=subprocess.run([*prefix,'env','LD_LIBRARY_PATH='+path(args.lib),path(binary)],capture_output=True)
    (args.output/'test.stdout.log').write_bytes(result.stdout);(args.output/'test.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('Actual SPI divisor/protocol test failed')
    lines=[json.loads(line) for line in result.stdout.decode().splitlines() if line.startswith('{')]
    assert len(lines)==9 and lines[-1]==dict(status='PASS',divisors=8,actual_completed_bytes=48,fast_byte_cycles=16)
    assert [row['byte_cycles'] for row in lines[:-1]]==[32,128,512,1024,16,64,256,512]
    if pins!={str(p):sha(p.read_bytes()) for p in inputs}:raise ValueError('Timing test inputs changed')
    save(args.output/'receipt-private.json',dict(status='PASS',source_sha256=pins,compiler=version,
        commands=[compile_spi,compile_test],binary_sha256=sha(binary.read_bytes()),test=lines,
        installed_library_modified=False,new_player_images=0))
    save(args.output/'attempt-private.json',dict(status='complete',test='SPI eight clock divisors',new_player_images=0))
    print(json.dumps(lines[-1]),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('include','lib','upstream','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--model-root',type=Path,default=ROOT/'tools/spi-flash-model')
    parser.add_argument('--wsl')
    args=parser.parse_args()
    for name in ('include','lib','upstream','output','model_root'):setattr(args,name,getattr(args,name).resolve())
    try:build(args)
    except Exception as exc:
        if args.output.is_dir():save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print(json.dumps(dict(status='FAILED',exception_type=type(exc).__name__)),flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
