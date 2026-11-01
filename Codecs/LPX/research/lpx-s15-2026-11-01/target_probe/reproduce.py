"""Prepare frozen copied sources, optionally link the unpaced Tiny88 images.

All generated sources, bindings, audio and binaries go under a fresh ignored
repository build directory. No production file or Git index is modified.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

BASE = '28620b5f16e3a698fb4085f1edea9e7d43847d24'
SOURCE = 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src'
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(repo, output):
    if output.exists() or repo/'build' not in output.parents:
        raise ValueError('Use a fresh output directory under repository build/')
    output.mkdir(parents=True)
    names = subprocess.check_output(['git', 'ls-tree', '--name-only', BASE+':'+SOURCE],
                                    cwd=repo, text=True).splitlines()
    for folder in (output/'baseline', output/'src'):
        folder.mkdir()
        for name in names:
            data = subprocess.check_output(['git', 'show', BASE+':'+SOURCE+'/'+name], cwd=repo)
            (folder/name).write_bytes(data)
    # The historical patch has CRLF line endings. Preserve it in the archive;
    # normalize a disposable copy and the two touched files for git apply.
    patch = output/'apply-lf.patch'
    patch.write_bytes((HERE/'s15-direct.patch').read_bytes().replace(b'\r\n', b'\n'))
    for name in ('Lpx4HybridCore.h', 'Lpx4HybridCore.cpp'):
        file = output/'src'/name
        file.write_bytes(file.read_bytes().replace(b'\r\n', b'\n'))
    prefix = (output/'src').relative_to(repo).as_posix()
    command = ['git', '-c', 'core.autocrlf=false', 'apply', '--directory', prefix,
               '-p1', str(patch)]
    subprocess.run([*command[:4], '--check', *command[4:]], cwd=repo, check=True)
    subprocess.run(command, cwd=repo, check=True)
    for name in ('Lpx4HybridCore.h', 'Lpx4HybridCore.cpp'):
        file = output/'src'/name
        file.write_bytes(file.read_bytes().replace(b'\r\n', b'\n'))
    for name in names:
        if name not in ('Lpx4HybridCore.h', 'Lpx4HybridCore.cpp'):
            assert (output/'baseline'/name).read_bytes() == (output/'src'/name).read_bytes()
    shutil.copyfile(HERE/'timing.cpp', output/'timing.cpp')
    binding = dict(status='prepared', base_commit=BASE,
                   archived_patch_sha256=digest(HERE/'s15-direct.patch'),
                   baseline={p.name:digest(p) for p in (output/'baseline').iterdir()},
                   prototype={p.name:digest(p) for p in (output/'src').iterdir()})
    (output/'source-private.json').write_text(json.dumps(binding, indent=2)+'\n')
    return binding


def build(repo, output, compiler, input_path):
    if input_path is None:
        raise ValueError('--input is required with --build')
    binding = json.loads((output/'source-private.json').read_text())
    def check_sources():
        for folder, key in (('baseline', 'baseline'), ('src', 'prototype')):
            assert all(digest(output/folder/name) == expected
                       for name, expected in binding[key].items())
    check_sources()
    blob = input_path.read_bytes()
    if len(blob) != 417 or blob[:6] != b'L4HY\x08\x0f' or int.from_bytes(blob[8:12], 'little') != 19200:
        raise ValueError('Historical size recipe requires the complete417-byte19200-sample S15 example')
    (output/'audio.inc').write_text(','.join(str(x) for x in blob)+'\n')
    flags = ['-mmcu=attiny88', '-DF_CPU=16000000UL', '-Os', '-flto', '-mcall-prologues',
             '-mrelax', '-fno-jump-tables', '-fno-exceptions', '-fno-rtti',
             '-ffunction-sections', '-fdata-sections', '-std=gnu++11',
             '-DLPX4_ENABLE_SPEECH=1', '-DLPX4_ENABLE_SPEECH_COMPACT=1',
             '-DLPX4_COMPACT_ONLY=1', '-DLPX4_ENABLE_ASM=0', '-DLPX4_MEMORY_PROFILE=1',
             '-DLPX4_FUNCTION_TUNING=0', '-DLPX4_AVR_DOT_UNROLL=1', '-DLPX3_LPC_SEGMENTS=2',
             '-I'+str(repo/'ATtiny88/Music/universal/vendor/include')]
    def tool(name):
        suffix = '.exe' if compiler.suffix.lower() == '.exe' else ''
        return str(compiler.with_name(name+suffix))
    rows = []
    for name, source, enabled in (('baseline-disabled', output/'baseline', 0),
                                  ('prototype-disabled', output/'src', 0),
                                  ('s15-direct', output/'src', 1)):
        out = output/name
        cmd = [str(compiler), *flags, '-DLPX4_ENABLE_S15='+str(enabled),
               '-I'+str(source), '-I'+str(output), str(output/'timing.cpp'),
               str(source/'Lpx4HybridCore.cpp'), '-Wl,--gc-sections,-Map='+str(out)+'.map',
               '-o', str(out)+'.elf']
        result = subprocess.run(cmd, capture_output=True)
        Path(str(out)+'-build-private.log').write_bytes(result.stdout+result.stderr)
        if result.returncode:
            raise RuntimeError('Compile failed; inspect ignored build log')
        subprocess.run([tool('avr-objcopy'), '-O', 'binary', str(out)+'.elf', str(out)+'.bin'],
                       check=True, capture_output=True)
        nm = subprocess.check_output([tool('avr-nm'), '-n', '-S', str(out)+'.elf'], text=True)
        Path(str(out)+'.nm').write_text(nm)
        text = subprocess.check_output([tool('avr-size'), '-A', str(out)+'.elf'], text=True)
        sec = {r.split()[0]:int(r.split()[1]) for r in text.splitlines()
               if r.startswith(('.text', '.data', '.bss'))}
        audio = [r.split() for r in nm.splitlines() if r.split()[-1:] == ['_ZL5audio']]
        assert len(audio) == 1 and int(audio[0][1], 16) == len(blob)
        image = Path(str(out)+'.bin').read_bytes()
        at = int(audio[0][0], 16)
        assert image[at:at+len(blob)] == blob and image.count(blob) == 1
        rows.append(dict(variant=name, full_flash_bytes=sec['.text']+sec['.data'],
                         audio_flash_bytes=len(blob),
                         program_flash_bytes_excluding_audio=sec['.text']+sec['.data']-len(blob),
                         static_ram_bytes=sec['.data']+sec['.bss']))
    assert (output/'baseline-disabled.bin').read_bytes() == (output/'prototype-disabled.bin').read_bytes()
    check_sources()
    result = dict(status='PASS', kind='unpaced-test-image', flag0_image_byte_identical=True,
                  flags=flags, rows=rows, input_sha256=digest(input_path),
                  compiler_sha256=digest(compiler), no_irq_or_realtime_admission=True)
    (output/'target-build-private.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(status='PASS', rows=rows)))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--build', action='store_true')
    ap.add_argument('--compiler', type=Path)
    ap.add_argument('--input', type=Path)
    a = ap.parse_args()
    repo, output = a.repo.resolve(), a.output.resolve()
    if a.build and a.compiler is None:
        raise ValueError('--compiler is required with --build')
    binding = prepare(repo, output)
    if a.build:
        build(repo, output, a.compiler.resolve(), a.input.resolve() if a.input else None)
    else:
        print(json.dumps(dict(status=binding['status'], base_commit=BASE)))
