#!/usr/bin/env python3
"""Link real AVR ELF/HEX, simulate full PWM/IRQ firmware, verify valid PWM bytes.

Requires AVR-GCC/AVR-LibC and a sim_profile runner compiled from
../../validation/atmega328p/sim_profile.c against simavr 1.6 + libelf.
On Windows the runner can execute in --wsl Ubuntu; dependencies can remain
in an external/ignored build tree. Does not flash or access a physical board.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from batch_decoder import BatchSession

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT.parent / 'validation/atmega328p'


def linux_path(path):
    path = Path(path).resolve()
    if os.name != 'nt':
        return str(path)
    if not re.match(r'^[A-Za-z]:$', path.drive):
        raise ValueError('WSL profiling requires a local drive path')
    return '/mnt/' + path.drive[0].lower() + '/' + '/'.join(path.parts[1:])


def run(source, output, avr_bin, sim_runner, sim_lib_dir=None, wsl=None):
    source, output, avr_bin = Path(source), Path(output).resolve(), Path(avr_bin)
    blob = source.read_bytes()
    if blob[:6] != b'L4HY\x02\x03' or not 20 <= len(blob) <= 65535:
        raise ValueError('Expected an L4HY v2 Q0 stream')
    samples = int.from_bytes(blob[8:12], 'little')
    if not 1 <= samples <= 64000:
        raise ValueError('Profile individual segments of 1..64000 samples')
    output.mkdir(parents=True, exist_ok=True)
    header = '#pragma once\n#include <stdint.h>\n#include <avr/pgmspace.h>\nstatic const uint8_t profile_voice[] PROGMEM = {\n'
    header += '\n'.join(','.join(str(v) for v in blob[i:i + 24]) + ',' for i in range(0, len(blob), 24)) + '\n};\n'
    (output / 'voice_data.h').write_bytes(header.encode())
    suffix = '.exe' if os.name == 'nt' else ''
    compiler = avr_bin / ('avr-g++' + suffix)
    elf, hexfile = output / 'profile.elf', output / 'profile.hex'
    command = [str(compiler), '-mmcu=atmega328p', '-DF_CPU=16000000UL', '-Os', '-std=gnu++11',
               '-fno-exceptions', '-fno-rtti', '-I' + str(ROOT / 'src'), '-I' + str(output),
               str(HARNESS / 'profile.cpp'), str(ROOT / 'src/Lpx4HybridCore.cpp'),
               '-Wl,-Map=' + str(output / 'profile.map'), '-o', str(elf)]
    subprocess.run(command, check=True, capture_output=True)
    subprocess.run([str(avr_bin / ('avr-objcopy' + suffix)), '-O', 'ihex', '-R', '.eeprom', str(elf), str(hexfile)], check=True)
    sizes = subprocess.check_output([str(avr_bin / ('avr-size' + suffix)), str(elf)], text=True)
    match = re.search(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+', sizes, re.M)
    if match is None:
        raise RuntimeError('Cannot parse avr-size output')
    text, data, bss = map(int, match.groups())
    timing = output / 'timing.json'
    valid = output / 'valid.pcm8'
    if wsl:
        command = ['wsl', '-d', wsl, '--', 'env']
        if sim_lib_dir:
            command.append('LD_LIBRARY_PATH=' + linux_path(sim_lib_dir))
        command += [linux_path(sim_runner), linux_path(elf), linux_path(valid), linux_path(timing)]
        subprocess.run(command, check=True, capture_output=True)
    else:
        environment = os.environ.copy()
        if sim_lib_dir:
            environment['LD_LIBRARY_PATH'] = str(Path(sim_lib_dir).resolve())
        subprocess.run([str(Path(sim_runner).resolve()), str(elf), str(valid), str(timing)],
                       check=True, env=environment, capture_output=True)
    report = json.loads(timing.read_text())
    with BatchSession('batch') as decoder:
        expected = decoder.decode_one(blob, samples)
    actual = valid.read_bytes()
    if expected is None or actual != expected.tobytes() or report['played'] != samples:
        raise AssertionError('Complete AVR/native PWM output mismatch')
    if report['timer_ticks'] != samples + report['underruns'] or report['decode_calls'] != samples:
        raise AssertionError('Simulation counters do not describe the complete stream')
    report.update(input_sha256=hashlib.sha256(blob).hexdigest(), input_bytes=len(blob), input_samples=samples,
                  pwm_sha256=hashlib.sha256(actual).hexdigest(), pwm_native_exact=True,
                  core_sha256=hashlib.sha256((ROOT / 'src/Lpx4HybridCore.cpp').read_bytes()).hexdigest(),
                  harness_sha256=hashlib.sha256((HARNESS / 'profile.cpp').read_bytes()).hexdigest(),
                  runner_sha256=hashlib.sha256((HARNESS / 'sim_profile.c').read_bytes()).hexdigest(),
                  elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(), hex_sha256=hashlib.sha256(hexfile.read_bytes()).hexdigest(),
                  flash_bytes=text + data, static_sram_bytes=data + bss,
                  compiler=subprocess.check_output([str(compiler), '--version'], text=True).splitlines()[0],
                  compiler_options=['-mmcu=atmega328p', '-DF_CPU=16000000UL', '-Os', '-std=gnu++11', '-fno-exceptions', '-fno-rtti'],
                  simavr_no_underrun=report['underruns'] == 0,
                  physical_hardware_measured=False,
                  instrumentation='Decode wall intervals include active IRQ and flag stores; PB0 marks OCR2B writes; queue sampled every 160 ticks.')
    report['mean_decode_wall_cycles'] = report['decode_wall_cycles_total'] / report['decode_calls']
    report['mean_160_sample_max_cycles_per_sample'] = report['decode_wall_cycles_max_160'] / 160
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('input', type=Path);ap.add_argument('output_directory', type=Path)
    ap.add_argument('--avr-bin', type=Path, required=True)
    ap.add_argument('--sim-runner', type=Path, required=True)
    ap.add_argument('--sim-lib-dir', type=Path)
    ap.add_argument('--wsl')
    a = ap.parse_args()
    r = run(a.input, a.output_directory, a.avr_bin, a.sim_runner, a.sim_lib_dir, a.wsl)
    print(json.dumps({k: r[k] for k in ('input_samples', 'underruns', 'mean_decode_wall_cycles', 'decode_wall_cycles_max',
                                       'flash_bytes', 'static_sram_bytes', 'pwm_native_exact')}, indent=2))
