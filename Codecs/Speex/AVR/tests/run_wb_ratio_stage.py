#!/usr/bin/env python3
"""Build/run matched ASM ratio-divider stages; never execute a full C decoder."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/speed-next'
PROFILES = {'wb395': 10, 'wb575': 15, 'wb775': 20, 'wb98': 25, 'wb128': 32}
LOADS = {'wb395': 25600, 'wb575': 9600, 'wb775': 9600, 'wb98': 25600, 'wb128': 25600}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def controls(args):
    if not args.avr_gcc or not args.cc or args.source_root.resolve() == ROOT:
        raise ValueError('controls requires --avr-gcc, --cc and --source-root at baseline 9772b0a4')
    rows = []
    for epoch, source in [('before', args.source_root), ('after', ROOT)]:
        folder = OUT / ('c-' + epoch)
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / 'build.log').open('w', encoding='utf-8') as log:
            subprocess.run([sys.executable, source / 'tools/build_wb.py', '--avr-gcc', args.avr_gcc,
                '--backend', 'c', '--low-rates', '7', '--enable-nb4', '--packet-bytes', '10', '--out', folder],
                stdout=log, stderr=subprocess.STDOUT, check=True)
        files = [path for part in ['src', 'tools', 'patches', 'vendor', 'handoff/upstream/tools']
                 for path in (source / part).rglob('*') if path.is_file() and '__pycache__' not in path.parts]
        save(OUT / (epoch + '-source.json'), {path.relative_to(source).as_posix():
             sha(path.read_bytes().replace(b'\r\n', b'\n')) for path in sorted(files)})
        data = (folder / 'wb.bin').read_bytes()
        rows.append(dict(epoch=epoch, binarySha256=sha(data), flashBytes=len(data), compileLinkedOnly=True))
    folder = OUT / 'baseline-rebuild'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / 'build.log').open('w', encoding='utf-8') as log:
        subprocess.run([sys.executable, args.source_root / 'tools/build_wb.py', '--avr-gcc', args.avr_gcc,
            '--backend', 'asm', '--low-rates', '7', '--enable-nb4', '--packet-bytes', '10', '--out', folder],
            stdout=log, stderr=subprocess.STDOUT, check=True)
    assert (folder / 'wb.bin').read_bytes() == (OUT / 'before/wb395/wb.bin').read_bytes()
    save(OUT / 'c-controls.json', dict(images=rows, baselineRevision='9772b0a4',
         baselineAsmRebuiltIdentically=True, cDecoderExecuted=False))
    folder = OUT / 'export'
    # Exporter deliberately refuses an existing destination. Use a fresh stage
    # directory for reproduction rather than deleting prior evidence.
    subprocess.run([sys.executable, ROOT / 'tools/build_wb.py', '--export-c', folder,
        '--low-rates', '7', '--enable-nb4'], check=True)
    manifest = json.loads((folder / 'sources.json').read_text(encoding='utf-8'))
    assert len(manifest['sources']) == len(set(manifest['sources'])) == 21
    assert not list(folder.rglob('*.S'))
    shim = folder / 'link_only.c'
    windows = sys.platform == 'win32'
    code = '''#include "speex_nb.h"
#include "speex_wb1.h"
static void sink(const int16_t *p,uint8_t n,void *ctx){(void)p;(void)n;(void)ctx;}
EXPORT_API int link_all(const uint8_t *p,size_t n,int16_t *out,int wb)
{return wb?speex_wb1_decode(p,n,sink,0):speex_nb_decode(p,n,out);}
EXPORT_API size_t link_init(void)
{speex_wb1_init();return speex_wb1_state_bytes()+speex_nb_state_bytes();}
'''
    shim.write_text(code.replace('EXPORT_API ', '__declspec(dllexport) ' if windows else ''), encoding='utf-8')
    artifact = folder / ('link_only.dll' if windows else 'link_only.so')
    subprocess.run([args.cc, '-std=c11', '-O2', '-fwrapv', '-fno-strict-aliasing', '-shared',
        *([] if windows else ['-fPIC']), '-Wno-pointer-to-int-cast', *['-D' + d for d in manifest['definitions']],
        *['-I' + str(folder / p) for p in manifest['includeDirectories']],
        *[folder / p for p in manifest['sources']], shim, '-o', artifact], check=True)
    save(OUT / 'export.json', dict(scope='Portable C11 export compile/link only; no C decoder execution or timing',
        compiler=subprocess.check_output([args.cc, '--version'], text=True).splitlines()[0], sources=21,
        duplicateSources=False, handwrittenAssembly=False, widebandBitrates=sorted(manifest['widebandBitrates']),
        artifactSha256=sha(artifact.read_bytes())))


def prepare(args):
    rows = []

    def retain(profile, name, raw, pcm, provenance):
        width = PROFILES[profile]
        assert len(raw) % width == 0 and len(pcm) == len(raw) // width * 640
        frames = len(raw) // width
        assert frames and all(raw[i] >> 3 == {10: 1, 15: 8, 20: 2, 25: 3, 32: 4}[width]
                              for i in range(0, len(raw), width))
        for kind, limit in [('full', frames), ('screen', min(64, frames))]:
            folder = OUT / 'data' / kind / profile
            for sub, suffix, data in [('streams', '.spxraw', raw[:limit * width]),
                                      ('oracle', '.pcm', pcm[:limit * 640])]:
                path = folder / sub / (name + suffix)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        rows.append(dict(profile=profile, stream=name, frames=frames,
                         inputSha256=sha(raw), pcmSha256=sha(pcm), provenance=provenance))

    for profile in ['wb395', 'wb575', 'wb775']:
        for raw in sorted((args.low_corpus / profile / 'streams').glob('*.spxraw')):
            retain(profile, raw.stem, raw.read_bytes(),
                   (args.low_corpus / profile / 'oracle' / (raw.stem + '.pcm')).read_bytes(),
                   'Existing independent compact-QMF corpus')
    retain('wb128', 'long', (args.spi_corpus / 'wb128/long.spxraw').read_bytes(),
           (args.spi_corpus / 'wb128/long.pcm').read_bytes(),
           'Existing independent continuous-history SPI corpus; RU/EN speech')
    for clip in ['chego', 'otvechaesh', 'vinni']:
        folder = args.gallery_root / clip / 'wb98'
        retain('wb98', clip, (folder / 'wb98.spxraw').read_bytes(),
               (folder / 'decoder.pcm').read_bytes(), 'Historical published-gallery ASM capture')
    folder = args.dialogue_root / 'wb98'
    retain('wb98', 'dialogue', (folder / 'wb98.spxraw').read_bytes(),
           (folder / 'decoder.pcm').read_bytes(), 'Historical published-dialogue ASM capture')
    assert {r['profile'] for r in rows} == set(PROFILES)
    save(OUT / 'data/manifest.json', dict(streams=rows,
         limits=['Original legacy WB9.8/WB12.8 full corpus is unavailable in current worktrees.',
                 'WB9.8 uses historical ASM captures, not a new independent oracle.',
                 'No C decoder runs or new audio encoding.']))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase', choices=['prepare', 'build', 'controls', 'raw', 'irq'], required=True)
    p.add_argument('--epoch', choices=['before', 'after'], default='after')
    p.add_argument('--screen', action='store_true')
    p.add_argument('--profiles', nargs='+', choices=list(PROFILES), default=list(PROFILES))
    p.add_argument('--avr-gcc')
    p.add_argument('--node')
    p.add_argument('--cc', help='Host C compiler for compile/link-only export check')
    p.add_argument('--source-root', type=Path, default=ROOT)
    p.add_argument('--workers', type=int, choices=range(1, 5), default=2)
    for name in ['low-corpus', 'spi-corpus', 'gallery-root', 'dialogue-root']:
        p.add_argument('--' + name, type=Path)
    args = p.parse_args()
    if args.phase == 'controls':
        controls(args)
        return
    if args.phase == 'prepare':
        if not all([args.low_corpus, args.spi_corpus, args.gallery_root, args.dialogue_root]):
            p.error('prepare needs all four corpus paths')
        prepare(args)
        print('Prepared retained inputs/oracles without encoding or C decoder execution')
        return
    if args.phase == 'build':
        if not args.avr_gcc:
            p.error('build needs --avr-gcc')
        for profile in args.profiles:
            folder = OUT / args.epoch / profile
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / 'build.log').open('w', encoding='utf-8') as log:
                subprocess.run([sys.executable, args.source_root / 'tools/build_wb.py',
                    '--avr-gcc', args.avr_gcc, '--backend', 'asm', '--enable-nb4', '--low-rates', '7',
                    '--packet-bytes', str(PROFILES[profile]), '--out', folder],
                    stdout=log, stderr=subprocess.STDOUT, check=True)
            # Source digest binds every relevant checked-in source, including C fallback.
            files = [path for part in ['src', 'tools', 'patches', 'vendor']
                     for path in (args.source_root / part).rglob('*')
                     if path.is_file() and '__pycache__' not in path.parts]
            save(folder / 'source.json', {path.relative_to(args.source_root).as_posix():
                 sha(path.read_bytes().replace(b'\r\n', b'\n')) for path in sorted(files)})
            with (folder / 'irq-build.log').open('w', encoding='utf-8') as log:
                if args.epoch == 'after':
                    subprocess.run([sys.executable, ROOT / 'tools/build_wb_stream_test.py',
                        '--avr-gcc', args.avr_gcc, '--packet-bytes', str(PROFILES[profile]),
                        '--low-rates', '7', '--enable-nb4', '--frame-load-cycles', str(LOADS[profile]),
                        '--out', OUT / 'irq' / profile], stdout=log, stderr=subprocess.STDOUT, check=True)
            print('Built', args.epoch, profile, flush=True)
        return
    if not args.node:
        p.error('run needs --node')

    def run(profile):
        source = OUT / ('irq' if args.phase == 'irq' else args.epoch) / profile
        kind = 'screen' if args.screen else 'full'
        folder = OUT / 'runs' / kind / ('irq' if args.phase == 'irq' else args.epoch) / profile
        folder.mkdir(parents=True, exist_ok=True)
        for name in ['backend.json', 'symbols.txt', 'wb.bin']:
            shutil.copyfile(source / name, folder / name)
        data = OUT / 'data' / kind / profile
        test = 'verify_wb_stream.mjs' if args.phase == 'irq' else 'verify_wb.mjs'
        with (folder / 'run.log').open('w', encoding='utf-8') as log:
            subprocess.run([args.node, ROOT / 'tests' / test, '--firmware', folder,
                '--streams', data / 'streams', '--oracle', data / 'oracle',
                *(['--packet-timing'] if args.phase == 'raw' else [])],
                stdout=log, stderr=subprocess.STDOUT, check=True)
        print('PASS', kind, args.phase, args.epoch, profile, flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run, args.profiles))


if __name__ == '__main__':
    main()
