#!/usr/bin/env python3
"""Verify imported CRC research in an isolated, ignored build directory."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
BUILD = (REPO / 'build' / 'crc-verification').resolve()
BOOTSTRAP = ('import sys,runpy; from pathlib import Path; '
             'sys.argv=sys.argv[1:]; sys.path.insert(0,str(Path(sys.argv[0]).parent)); '
             'runpy.run_path(sys.argv[0],run_name="__main__")')


def main():
    provenance = json.loads((ROOT / 'SOURCES.json').read_text(encoding='utf-8'))
    imported = [row for row in provenance['files'] if row['status'] == 'imported']
    for row in imported:
        path = ROOT / row['path']
        assert path.resolve().is_relative_to(ROOT), path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row.get('current_sha256', row['sha256']), path
    print(f'PASS: {len(imported)} files match archive SHA-256 or documented Intel audit corrections', flush=True)
    integrity = ROOT / 'SHA256SUMS.txt'
    if integrity.exists():
        for line in integrity.read_text(encoding='utf-8').splitlines():
            digest, name = line.split('  ', 1)
            path = (ROOT / name).resolve()
            assert path.is_relative_to(ROOT)
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
        print('PASS: collection integrity manifest', flush=True)

    BUILD.mkdir(parents=True, exist_ok=True)
    assert BUILD.is_relative_to((REPO / 'build').resolve())
    work = Path(tempfile.mkdtemp(prefix='run-', dir=BUILD)).resolve()
    assert work.is_relative_to(BUILD)
    for family in ('CRC16', 'CRC32'):
        shutil.copytree(ROOT / family, work / family)
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    results = []

    def run(label, command, cwd=work):
        print(f'CHECK: {label}', flush=True)
        result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                                capture_output=True, text=True, encoding='utf-8', timeout=300)
        output = result.stdout + result.stderr
        log = work / f'{len(results):02d}.log'
        log.write_text(output, encoding='utf-8')
        results.append({'check': label, 'exit_code': result.returncode, 'log': log.name})
        if result.returncode:
            raise RuntimeError(f'{label}\n{output}\nLogs: {work}')
        print(output[-2500:].rstrip(), flush=True)
        return output

    def py(label, path):
        return run(label, [sys.executable, '-X', 'utf8', '-c', BOOTSTRAP, path], path.parent)

    v6 = work / 'CRC16/research/10_pair_0025_0047_v6_minimal'
    v5 = work / 'CRC16/research/09_pair_0025_0047_v5_fast'
    (v6 / 'hex').mkdir(exist_ok=True)
    py('Dual CRC16 v6 ASM/BIN and ROM residues', v6 / 'tools/verify_and_build.py')
    py('Dual CRC16 v5 sources and polynomial math', v5 / 'tests/verify_sources_and_math.py')
    py('Dual CRC16 pair properties', work / 'CRC16/research/07_better_pair_0007_0021/verify_polynomials.py')

    # The frozen historical audit uses its original SELECTED_FIRMWARE layout.
    # Create that compatibility layout only in the disposable build copy.
    selected = work / 'CRC16/tools/SELECTED_FIRMWARE'
    selected.mkdir()
    choices = {
        'min41_RESET': v6 / 'bin/bitwise_shared_parity_reset.bin',
        'min42': v6 / 'bin/bitwise_shared_parity.bin',
        'mid57': v6 / 'bin/bitwise_shared_parity_u4.bin',
        'fast75': v5 / 'bin/fast75_peephole.bin',
        'fast82': v5 / 'bin/fast_p47_rotate.bin',
    }
    for suffix, path in choices.items():
        shutil.copyfile(path, selected / f'milestone_dual_0025_0047_{suffix}.bin')
    shutil.copyfile(work / 'CRC16/examples/dual_0025_0047_min42_64KiB.bin',
                    selected / 'milestone_dual_0025_0047_min42_DEMO_64KiB.bin')
    py('Independent polynomial and footer audit', work / 'CRC16/tools/audit_original.py')

    old = work / 'CRC32/research/04_crc32_ieee_castagnoli_comparison'
    spec = importlib.util.spec_from_file_location('historical_crc32', old / 'i8080_crc32_tools.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for stem, size in (('crc32_mpeg2_8080', 103), ('crc32_mpeg2_8080_compact', 78),
                       ('crc32c_msb_8080', 103), ('crc32c_msb_8080_compact', 78)):
        binary, _ = module.assemble((old / f'{stem}.asm').read_text(encoding='utf-8'))
        assert len(binary) == size and binary == (old / f'{stem}.bin').read_bytes()
    assert module.crc32(b'123456789', 0x04C11DB7) == 0x0376E6E7
    assert module.crc32(b'123456789', 0x1EDC6F41) == 0xFABBF0EA
    results.append({'check': 'Historical CRC32 four ASM/BIN pairs and two check vectors', 'exit_code': 0})

    no_table = work / 'CRC32/no-tables'
    py('Standard CRC32C no-table ROM generation', no_table / 'generate.py')
    py('Standard CRC32C cachedB generation', no_table / 'experiment_cached.py')
    py('Standard CRC32C machine-code check vector', no_table / 'golden_8080.py')
    py('CRC32C table generator: two 57-byte variants', work / 'CRC32/table-generator/verify.py')
    table = work / 'CRC32/checked-table'
    py('CRC32C checked table: Python instruction emulator', table / 'build.py')

    node = shutil.which('node') or str(REPO / 'build/toolchains/node-22.22.3/node.exe')
    native_cc = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    emcc = REPO / 'build/toolchains/emscripten-6.0.12/upstream/emscripten/emcc.py'
    if native_cc:
        compiler = [native_cc, '-O3', '-std=c11', '-Wall', '-Wextra']
        wasm = False
    elif emcc.exists():
        upstream = emcc.parents[1]
        config = work / 'emscripten-config.py'
        config.write_text(f'LLVM_ROOT = {str(upstream / "bin")!r}\n'
                          f'BINARYEN_ROOT = {str(upstream)!r}\n'
                          f'NODE_JS = [{str(node)!r}]\n', encoding='utf-8')
        env['EM_CONFIG'] = str(config)
        env['EM_CACHE'] = str(emcc.parent / 'cache')
        compiler_tmp = work / 'compiler-tmp'
        compiler_tmp.mkdir()
        env['TEMP'] = str(compiler_tmp)
        env['TMP'] = str(compiler_tmp)
        env['EMCC_TEMP_DIR'] = str(compiler_tmp)
        env['PATH'] = str(Path(node).parent) + os.pathsep + env.get('PATH', '')
        compiler = [sys.executable, '-X', 'utf8', '-c', BOOTSTRAP, emcc, '-O3', '-std=c11', '-Wall', '-Wextra',
                    '-sENVIRONMENT=node', '-sNODERAWFS=1', '-sEXIT_RUNTIME=1',
                    '-sSTACK_SIZE=1048576', '-sWASM_ASYNC_COMPILATION=0']
        wasm = True
    else:
        raise RuntimeError('A C compiler or the repository bundled Emscripten is required')

    def c_program(name, source):
        output = work / (name + ('.js' if wasm else ('.exe' if os.name == 'nt' else '')))
        run(f'Compile {name}', compiler + [source, '-o', output])
        return [node, output] if wasm else [output]

    compact = c_program('dual16-compact', v6 / 'tests/test_compact.c')
    for name in ('bitwise_shared', 'bitwise_shared_parity', 'bitwise_shared_parity_reset',
                 'bitwise_shared_parity_u2', 'bitwise_shared_parity_u4'):
        run(f'Dual CRC16 v6 {name}: full ROM and faults', compact + [v6 / f'bin/{name}.bin'])
    fast = c_program('dual16-fast', v5 / 'tests/bench8080.c')
    run('Dual CRC16 v5 fast75/fast82: full ROM and faults',
        fast + [v5 / 'bin/fast75_peephole.bin', v5 / 'bin/fast_p47_rotate.bin'])

    no_table_cpu = c_program('crc32c-no-table', no_table / 'emulate8080.c')
    firmware_count = 0
    fault_count = 0
    for kib in (24, 32):
        for name in ('u1_halt', 'cachedB', 'u2_halt', 'u4_halt', 'u8_halt'):
            rom = no_table / f'crc32c_8080_{kib}k_{name}.bin'
            out = run(f'CRC32C {kib} KiB {name}: good ROM', no_table_cpu + [rom])
            assert 'INTE=1' in out and 'CRCregs=00000000' in out
            firmware_count += 1
            for address in (512, 1091, kib * 512, kib * 1024 - 4, kib * 1024 - 1):
                bit = 8 * address + address % 8
                out = run(f'CRC32C {kib} KiB {name}: fault at {address:04X}', no_table_cpu + [rom, bit])
                assert 'INTE=0' in out
                fault_count += 1

    table_cpu = c_program('crc32c-checked-table', table / 'emulate8080.c')
    for kib in (24, 32):
        rom = table / f'crc32c_8080_checked_{kib}k.bin'
        run(f'CRC32C table {kib} KiB: C instruction emulator', table_cpu + [rom])
        run(f'CRC32C table {kib} KiB: all 8192 table bit flips', table_cpu + [rom, '--all-table-bits'])

    integration = work / 'CRC16/integration/no-ram-diagnostics'
    for mode in ('32K_A15_UNUSED', '64K_A15_CONNECTED'):
        py(f'Integrated diagnosis {mode}: rebuild', integration / mode / 'build.py')
        run(f'Integrated diagnosis {mode}: JavaScript CPU tests',
            [node, integration / mode / 'verify_8080.js'], integration / mode)

    run('Intel 8080 exhaustive flags and instruction checks', [node, ROOT / 'audit/test-intel-flags.mjs'])
    run('Intel 8080 firmware under audited flags and timings', [node, ROOT / 'audit/test-intel-firmware.mjs'])
    py('Legacy emulators reject unsupported DAA', ROOT / 'audit/test-legacy-guards.py')

    summary = {'imported_files_verified': len(imported), 'work_directory': str(work),
               'c_execution': 'Emscripten WASM under Node' if wasm else 'native C',
               'no_table_good_roms': firmware_count, 'no_table_faults': fault_count,
               'checks': results}
    report = work / 'results.json'
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PASS: all {len(results)} checks; report {report}', flush=True)


if __name__ == '__main__':
    main()
