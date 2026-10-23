#!/usr/bin/env python3
"""Rebuild frozen HQ4 assembly and verify all PCM using retained archive digests."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'ATtiny13A/Sound/codec'
MAP = ROOT / 'ATtiny13A/Sound/research/stages/hq4-balanced/SOURCE_MAP.json'
NAMES = ('chego', 'otvechaesh', 'vinni', 'chego_stoi_max')
EMULATE = r'''
const fs=require('fs'),crypto=require('crypto');
const [modulePath,programPath,length,expected]=process.argv.slice(1);
const {AVRCore}=require(modulePath);
const cpu=new AVRCore(fs.readFileSync(programPath));
const pcm=Buffer.alloc(Number(length));
for(let i=0;i<pcm.length;i++)pcm[i]=cpu.takeSample();
const sha=crypto.createHash('sha256').update(pcm).digest('hex');
if(sha!==expected||cpu.missedOverflows||cpu.irqCount!==pcm.length*5)process.exit(1);
console.log(JSON.stringify({samples:pcm.length,sha256:sha,missed_overflows:cpu.missedOverflows}));
'''


def run(args, cwd):
    result = subprocess.run(list(map(str, args)), cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avr-bin', type=Path, help='Directory containing avr-gcc and avr-objcopy')
    parser.add_argument('--node', default='node')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    suffix = '.exe' if os.name == 'nt' else ''
    avr_bin = args.avr_bin.resolve() if args.avr_bin else None
    compiler = avr_bin / ('avr-gcc' + suffix) if avr_bin else 'avr-gcc'
    objcopy = avr_bin / ('avr-objcopy' + suffix) if avr_bin else 'avr-objcopy'
    frozen = {r['path']: r for r in json.loads(MAP.read_text(encoding='utf-8'))['omitted']}
    work = ROOT / 'build/frozen-speech'
    results = {}
    for name in NAMES:
        folder = work / name
        folder.resolve().relative_to(ROOT.resolve())
        folder.mkdir(parents=True, exist_ok=True)
        for filename in ('firmware.S', 'speech.hq'):
            shutil.copyfile(SOURCE / 'release' / name / filename, folder / filename)
        run([compiler, '-mmcu=attiny13', '-nostdlib', '-Wl,-Ttext=0', '-x', 'assembler', 'firmware.S', '-o', 'firmware.elf'], folder)
        run([objcopy, '-O', 'binary', 'firmware.elf', 'firmware.bin'], folder)
        reference = frozen[f'release/{name}/firmware.bin']
        image = (folder / 'firmware.bin').read_bytes()
        # GNU aligns .text to two bytes; the archived Clang image can be odd-sized.
        padding = image[reference['bytes']:]
        assert len(padding) <= 1 and all(value in (0, 255) for value in padding), name
        image = image[:reference['bytes']]
        assert hashlib.sha256(image).hexdigest() == reference['sha256'], name
        (folder / 'firmware.bin').write_bytes(image)
        expected = frozen[f'release/{name}/expected.raw']
        pcm = json.loads(run([args.node, '-e', EMULATE, SOURCE / 'release/avr_emulator.js', folder / 'firmware.bin', expected['bytes'], expected['sha256']], folder))
        results[name] = {'flash_bytes': len(image), 'image_sha256': reference['sha256'], **pcm}
    report = {'pass': True, 'variants': results, 'total_samples': sum(r['samples'] for r in results.values()), 'hardware_tested': False}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
