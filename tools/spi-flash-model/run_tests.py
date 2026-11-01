"""Build the portable model as C11 and C++11, then run actual SPI contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    root = Path(__file__).resolve().parents[2]
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc', default=os.environ.get('CC', 'gcc'))
    parser.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--build-dir', type=Path, default=root/'build/spi-flash-model')
    args = parser.parse_args()
    cc, cxx = shutil.which(args.cc), shutil.which(args.cxx)
    if not cc or not cxx:
        raise ValueError('C and C++ host compilers are required')
    vendor = root/'third_party/qemu-m25p80'
    meta = json.loads((vendor/'PROVENANCE.json').read_text(encoding='utf-8'))
    for row in meta['files']:
        data = (vendor/row['vendored_path']).read_bytes()
        if len(data) != row['committed_bytes'] or hashlib.sha256(data).hexdigest() != row['committed_sha256']:
            raise ValueError('A verbatim QEMU source or license changed')
    upstream = (vendor/'upstream/m25p80.c').read_bytes()
    notice = upstream[:upstream.index(b'*/')+2]
    if not (here/'w25q128_readonly.c').read_bytes().startswith(notice):
        raise ValueError('Adapted source must preserve upstream copyright/license notice')
    args.build_dir.mkdir(parents=True, exist_ok=True)
    obj = args.build_dir/'w25q128_readonly.o'
    suffix = '.exe' if os.name == 'nt' else ''
    c_test, cpp_test = [args.build_dir/(name+suffix) for name in ('test_c_model', 'test_cpp_model')]
    common = ['-O2', '-Wall', '-Wextra', '-Werror', '-pedantic']
    subprocess.run([cc, '-x', 'c', '-std=c11', *common, '-c', str(here/'w25q128_readonly.c'), '-o', str(obj)], check=True)
    subprocess.run([cxx, '-std=c++11', *common, str(here/'test_w25q128_readonly.cpp'), str(obj), '-o', str(c_test)], check=True)
    subprocess.run([str(c_test.resolve())], check=True)
    subprocess.run([cxx, '-x', 'c++', '-std=c++11', *common, str(here/'w25q128_readonly.c'),
                    str(here/'test_w25q128_readonly.cpp'), '-o', str(cpp_test)], check=True)
    subprocess.run([str(cpp_test.resolve())], check=True)
    print(json.dumps(dict(status='passed', verbatim_source_and_license_hashes_verified=4,
        upstream_adapted_notice_exact=True, build_modes=['C11 with C++11 caller', 'C++11'],
        command_transfer_contracts_per_build=13, device_timing_simulated=False)))


if __name__ == '__main__':
    main()
