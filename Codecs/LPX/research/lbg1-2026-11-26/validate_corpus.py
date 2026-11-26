"""Validate actual encoded LG streams with ASan/UBSan and bounded read faults.

Run from Linux/WSL after experimental/LBG1/compare.py. Generated binaries and
receipts remain in ignored build/. No network or optional Python packages.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
EXPERIMENT = REPO / 'Codecs/LPX/experimental/LBG1'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='build/lbg1-encoder/manifest.json')
    args = parser.parse_args()
    manifest_path = REPO / args.manifest
    manifest_digest = sha(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    corpus = {}
    for case in manifest['cases']:
        for variant in case['variants'].values():
            path = REPO / variant['path']
            if sha(path) != variant['sha256']:
                raise ValueError('Corpus changed: ' + variant['path'])
            corpus[variant['path']] = variant['sha256']
    if not corpus:
        raise ValueError('Empty corpus')
    sources = [HERE / 'validate_corpus.py', HERE / 'corpus_fuzz.cpp',
               *EXPERIMENT.glob('decoder*'),
               *(REPO / 'Codecs/LPX/01_ACTIVE_Q0_CODEC/src').glob('*.h')]
    source_digests = {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(sources)}
    output = REPO / 'build/lbg1-validation'
    output.mkdir(parents=True, exist_ok=True)
    common = ['g++', '-O1', '-g', '-std=c++11', '-fsanitize=address,undefined',
              '-fno-omit-frame-pointer', '-DLPX4_ENABLE_ASM=0',
              '-DLPX4_COMPACT_VERSION=9',
              '-ICodecs/LPX/01_ACTIVE_Q0_CODEC/src', '-ICodecs/LPX/experimental/LBG1']
    environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    tests = {}
    for name, source, inputs in [
        ('boundaries', EXPERIMENT / 'decoder_test.cpp', []),
        ('corpus', HERE / 'corpus_fuzz.cpp', sorted(corpus)),
    ]:
        executable = output / name
        command = [*common, source.relative_to(REPO).as_posix(),
                   'Codecs/LPX/experimental/LBG1/decoder.cpp', '-o',
                   executable.relative_to(REPO).as_posix()]
        subprocess.run(command, cwd=REPO, check=True)
        result = subprocess.run([str(executable), *inputs], cwd=REPO,
                                env=environment, check=True, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        tests[name] = dict(command=command, stdout=result.stdout.strip(),
                           stderr=result.stderr, exit_code=result.returncode,
                           executable_sha256=sha(executable))
        print(name + ': ' + result.stdout.strip(), flush=True)
    if source_digests != {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(sources)}:
        raise ValueError('Validation sources changed during the run')
    if sha(manifest_path) != manifest_digest or any(sha(REPO / name) != digest for name, digest in corpus.items()):
        raise ValueError('Validation corpus or manifest changed during the run')
    receipt = dict(schema='lbg1-sanitized-corpus-validation-v1',
                   compiler=subprocess.check_output(['g++', '--version'], text=True).splitlines()[0],
                   manifest_sha256=manifest_digest, corpus=corpus, tests=tests,
                   sources=source_digests, pre_post_hashes_equal=True)
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n',
                                       encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
