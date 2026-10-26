#!/usr/bin/env python3
"""Compile C, AVR5 ASM and forced-generic arithmetic; run with active IRQ.

Requires sim_math built from ../../validation/atmega328p/sim_math.c with
simavr 1.6 + libelf. Generated firmware belongs in an ignored build folder.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def linux_path(path):
    p = Path(path).resolve()
    return '/mnt/' + p.drive[0].lower() + '/' + '/'.join(p.parts[1:]) if os.name == 'nt' else str(p)


def run(output, avr_bin, runner, lib=None, wsl=None,dot_unroll=9):
    output, avr_bin, runner = map(Path, (output, avr_bin, runner))
    output.mkdir(parents=True, exist_ok=True)
    compiler = avr_bin / ('avr-g++.exe' if os.name == 'nt' else 'avr-g++')
    results = []
    for name, flags, expected in [('c', ['-DLPX4_ENABLE_ASM=0'], 0),
            ('avr5', ['-DLPX4_ENABLE_ASM=1'], 1),
            ('forced-generic', ['-DLPX4_ENABLE_ASM=1','-DLPX4_ARCH=LPX4_ARCH_GENERIC'], 0)]:
        target = output / (name + '.elf')
        options = ['-mmcu=atmega328p','-DF_CPU=16000000UL','-Os','-std=gnu++11',
                   f'-DLPX4_AVR_DOT_UNROLL={dot_unroll}', *flags]
        subprocess.run([str(compiler),*options,'-I'+str(ROOT/'src'),
            str(ROOT/'tests/math_backend.cpp'),'-o',str(target)], check=True, capture_output=True)
        if wsl:
            command = ['wsl','-d',wsl,'--','env']
            if lib: command.append('LD_LIBRARY_PATH='+linux_path(lib))
            command += [linux_path(runner),linux_path(target)]
            result = subprocess.check_output(command,text=True)
        else:
            env = os.environ.copy()
            if lib: env['LD_LIBRARY_PATH'] = str(Path(lib).resolve())
            result = subprocess.check_output([str(runner.resolve()),str(target.resolve())],text=True,env=env)
        report = json.loads(next(line for line in result.splitlines() if line.startswith('{')))
        if report['cases'] != 5225096 or report['backend'] != expected or report['irqs'] < 100:
            raise AssertionError(report)
        if not report['done'] or report['error'] or report['zero_error']:
            raise AssertionError(report)
        report.update(name=name, compiler_options=options,
                      elf_sha256=hashlib.sha256(target.read_bytes()).hexdigest())
        results.append(report)
        print(name,report,flush=True)
    result = {'cpu':'ATmega328P / AVR5', 'simulator':'simavr 1.6','dot_unroll':dot_unroll,
              'compiler':subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0],
              'fixture_sha256':hashlib.sha256((ROOT/'tests/math_backend.cpp').read_bytes()).hexdigest(),
              'math_header_sha256':hashlib.sha256((ROOT/'src/Lpx4Math.h').read_bytes()).hexdigest(),
              'runner_source_sha256':hashlib.sha256((ROOT.parent/'validation/atmega328p/sim_math.c').read_bytes()).hexdigest(),
              'variants':results,'physical_hardware_measured':False}
    (output/'verification.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    return result


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output',type=Path);ap.add_argument('--avr-bin',type=Path,required=True)
    ap.add_argument('--sim-runner',type=Path,required=True);ap.add_argument('--sim-lib-dir',type=Path)
    ap.add_argument('--wsl')
    ap.add_argument('--dot-unroll',type=int,choices=(1,3,9),default=9)
    a=ap.parse_args();run(a.output,a.avr_bin,a.sim_runner,a.sim_lib_dir,a.wsl,a.dot_unroll)
