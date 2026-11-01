"""Build an isolated, divisor-tested byte-level SPI Flash player observer."""
import argparse
from pathlib import Path
import subprocess
import traceback
from types import SimpleNamespace

from build_cycle_test import HERE,ROOT,build as timing_test,linux,physical,sha,save


def build(args):
    if args.output.exists() or not args.output.is_relative_to(ROOT/'build'):
        raise ValueError('Use a fresh isolated SPI observer folder')
    args.output.mkdir(parents=True)
    save(args.output/'attempt-private.json',dict(status='running',new_player_images=0))
    timing_test(SimpleNamespace(**{**vars(args),'output':args.output/'timing-test'}))
    path=linux if args.wsl else str
    prefix=['wsl','-d',args.wsl,'--'] if args.wsl else []
    sources=[Path(__file__),HERE/'build_cycle_test.py',HERE/'patch_simavr_spi.py',HERE/'sim_spi_player.c',
        HERE/'spi_flash_bridge.c',HERE/'spi_flash_bridge.h',HERE/'simavr_spi_clock.h',HERE/'test_bridge.c',HERE/'player_hardware.cpp',
        args.model_root/'w25q128_readonly.c',args.model_root/'w25q128_readonly.h',
        args.output/'timing-test/avr_spi-clocked.c',args.output/'timing-test/avr_spi-clocked.o']
    sources += [p for p in args.include.rglob('*') if physical(p)]
    sources += [p for p in args.lib.glob('libsimavr*') if physical(p)]
    sources += [p for p in args.lib.glob('libelf*') if physical(p)]
    pins={str(p):sha(p.read_bytes()) for p in sources}
    binary=args.output/'sim_spi_player'
    command=[*prefix,'gcc','-O2','-std=c11','-Wall','-Wextra','-Werror',
        '-I'+path(args.include),'-I'+path(args.include.parent),'-I'+path(args.model_root),'-I'+path(HERE),
        path(HERE/'sim_spi_player.c'),path(HERE/'spi_flash_bridge.c'),path(args.model_root/'w25q128_readonly.c'),
        path(args.output/'timing-test/avr_spi-clocked.o'),'-L'+path(args.lib),'-lsimavr','-lelf','-lz','-lzstd','-o',path(binary)]
    result=subprocess.run(command,capture_output=True)
    (args.output/'compile.stdout.log').write_bytes(result.stdout);(args.output/'compile.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('SPI observer compilation failed')
    # The vendor metadata remains a separate object, never a firmware input.
    avr=lambda name:args.avr_bin/(name+'.exe' if (args.avr_bin/(name+'.exe')).exists() else name)
    hardware=args.output/'test-hardware.o';hardware_bin=args.output/'test-hardware.bin'
    subprocess.run([str(avr('avr-g++')),'-mmcu=atmega328p','-Os','-std=gnu++11',
        '-I'+str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/examples/AVR_V5_PLAYER'),'-c',str(HERE/'player_hardware.cpp'),
        '-o',str(hardware)],check=True,capture_output=True)
    subprocess.run([str(avr('avr-objcopy')),'-O','binary','-j','.progmem.data',str(hardware),str(hardware_bin)],
                   check=True,capture_output=True)
    bridge_test=args.output/'test_spi_bridge'
    bridge_command=[*prefix,'gcc','-O2','-std=c11','-Wall','-Wextra','-Werror',
        '-I'+path(args.include),'-I'+path(args.include.parent),'-I'+path(args.model_root),'-I'+path(HERE),
        path(HERE/'test_bridge.c'),path(HERE/'spi_flash_bridge.c'),path(args.model_root/'w25q128_readonly.c'),
        path(args.output/'timing-test/avr_spi-clocked.o'),'-L'+path(args.lib),'-lsimavr','-lelf','-lz','-lzstd','-o',path(bridge_test)]
    result=subprocess.run(bridge_command,capture_output=True)
    (args.output/'bridge-compile.stdout.log').write_bytes(result.stdout);(args.output/'bridge-compile.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('SPI bridge unit compilation failed')
    result=subprocess.run([*prefix,'env','LD_LIBRARY_PATH='+path(args.lib),path(bridge_test),path(hardware_bin)],capture_output=True)
    (args.output/'bridge-test.stdout.log').write_bytes(result.stdout);(args.output/'bridge-test.stderr.log').write_bytes(result.stderr)
    if result.returncode:raise RuntimeError('Actual GPIO/clocked-byte bridge contract failed')
    if pins!={str(p):sha(p.read_bytes()) for p in sources}:raise ValueError('Observer source changed during compilation')
    save(args.output/'receipt-private.json',dict(status='built-not-player-admitted',source_sha256=pins,
        binary_sha256=sha(binary.read_bytes()),command=command,bridge_test_command=bridge_command,
        bridge_test_binary_sha256=sha(bridge_test.read_bytes()),bridge_test_stdout_sha256=sha(result.stdout),installed_library_modified=False,
        spi_module_installation='explicit existing SPDR write-handler replacement',new_player_images=0))
    save(args.output/'attempt-private.json',dict(status='complete',new_player_images=0))
    print('{"status":"SPI observer built, timing unit PASS","new_player_images":0}',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('include','lib','upstream','output','avr-bin'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--model-root',type=Path,default=ROOT/'tools/spi-flash-model')
    parser.add_argument('--wsl')
    args=parser.parse_args()
    for name in ('include','lib','upstream','output','model_root','avr_bin'):setattr(args,name,getattr(args,name).resolve())
    try:build(args)
    except Exception as exc:
        if args.output.is_dir():save(args.output/'failure-private.json',dict(exception_type=type(exc).__name__,traceback=traceback.format_exc()))
        print('{"status":"FAILED","phase":"SPI observer build"}',flush=True);return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
