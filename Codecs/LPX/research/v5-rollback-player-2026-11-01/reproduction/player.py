"""Separate fixed four-row current-source ROM gate; execution needs prior review."""
from __future__ import annotations

import argparse
from collections import Counter
import ctypes as ct
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time
import traceback
from types import SimpleNamespace

from policy import PRODUCTION, SAMPLES, RESETS, BYTES, sha, normalize, require, rows, geometry, report_ok

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
ROOT = HERE.parents[4]
ACTIVE = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
SPI = PACKAGE.parent / 'v5-external-spi-player-2026-11-01/reproduction'
STRICT = PACKAGE.parent / 'v5-adaptive-target-player-2026-10-30/reproduction'
RATE = PACKAGE.parent / 'v5-joint-rate-2026-11-01'
SHARED = PACKAGE.parent / 'v5-matched-search-cpu-2026-10-30'
VAL = ROOT / 'Codecs/LPX/validation/atmega328p'


def save(path, value):
    path = Path(path).resolve()
    require(path.is_relative_to(ROOT / 'build') and not path.is_symlink()
            and not (path.exists() and path.stat().st_nlink > 1), 'Use distinct ignored private outputs')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.writing')
    require(not temporary.exists() and not temporary.is_symlink(), 'Preserve an incomplete metadata write')
    with temporary.open('xb') as stream:
        stream.write((json.dumps(value, indent=2, allow_nan=False) + '\n').encode())
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32) or attempt == 5: raise
            time.sleep(.01 * (attempt + 1))


class Inputs:
    def __init__(self): self.pins = {}
    def read(self, path, digest=None):
        path = Path(path).resolve(); raw = path.read_bytes(); actual = sha(raw)
        require(digest is None or actual == digest, 'A bound input/source changed')
        require(str(path) not in self.pins or self.pins[str(path)] == actual, 'An input changed during preparation')
        self.pins[str(path)] = actual
        return raw
    def json(self, path, digest=None): return json.loads(self.read(path, digest))
    def verify(self):
        require(all(sha(Path(p).read_bytes()) == d for p, d in self.pins.items()), 'A pinned input changed')


def sources():
    paths = [*(ACTIVE / 'src').rglob('*'), *(ACTIVE / 'tools').glob('*.py'),
             *(ACTIVE / 'examples/AVR_V5_PLAYER').glob('*'),
             ACTIVE / 'tests/input_callback_native.cpp', ACTIVE / 'tests/test_speech_v4.py',
             VAL / 'sim_player.c', VAL / 'player_hardware.cpp', *HERE.glob('*.py'), PACKAGE / 'PROTOCOL.md',
             *SPI.glob('*.py'), STRICT / 'admit.py', STRICT / 'player_evidence.py',
             *(RATE / name for name in ('pilot_runtime.py', 'pilot_policy.py', 'baselines.py')),
             *(SHARED / name for name in ('study_runtime.py', 'study_policy.py'))]
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(set(paths)) if p.is_file()}


def archive_inventory(commit, inventory):
    targets = sorted({name.rsplit('/', 1)[0] for name in inventory})
    raw = subprocess.check_output(['git', '-C', str(ROOT), 'archive', '--format=tar', commit, '--', *targets])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name: sha(archive.extractfile(m).read()) for m in archive if m.isfile() and m.name in inventory}


def bind_sources(commit, inputs):
    inventory = sources()
    require(archive_inventory(commit, inventory) == inventory, 'The adapter/source commit differs from executing bytes')
    original = {k: v for k, v in inventory.items() if not k.startswith(PACKAGE.relative_to(ROOT).as_posix() + '/')}
    require(archive_inventory(PRODUCTION, original) == original, 'Frozen production/established helpers changed')
    for path, digest in inventory.items(): inputs.read(ROOT / path, digest)
    return inventory


def operators():
    # Deliberately deferred: importing this file or pure policy contracts must
    # never initialize numerical/native reference work or compiler queries.
    for tree in (ROOT.parents[1] / 'build/codec-python', ROOT.parents[1] / 'build/codec-plot'):
        if tree.is_dir(): sys.path.append(str(tree))
    sys.path[:0] = [str(SPI), str(RATE), str(ACTIVE / 'tools')]
    import spi_player
    import native_inputs
    import pilot_runtime
    require(spi_player.ROOT.resolve() == ROOT.resolve(), 'Wrong current-source ROM helper')
    require(Path(native_inputs.__file__).resolve() == (SPI / 'native_inputs.py').resolve(), 'Wrong native helper')
    require(Path(pilot_runtime.__file__).resolve() == (RATE / 'pilot_runtime.py').resolve(), 'Wrong native bridge')
    return SimpleNamespace(rom=spi_player.rom, bench=spi_player.bench, spi=spi_player,
                           native=native_inputs, runtime=pilot_runtime)


def select_point(args, inputs):
    marker = inputs.json(args.selection.parent / 'complete-private.json')
    closed = inputs.json(args.selection.parent / 'binding-private.json', marker['binding_sha256'])
    point = inputs.json(args.selection)
    require(marker['status'] == 'complete' and closed['status'] == 'PASS'
            and point['schema'] == 'lpx-extra-rollback-useful-tuples-private-v1'
            and point['status'] == 'PASS' and point['source_commit'] == PRODUCTION
            and len(point['tuples']) == 1, 'Require the final single-useful-tuple all-point export')
    require(set(point['producer_paths']) == {'continue', 'rollback'} and closed['production_sources'],
            'Both producer/source closures are required')
    for path, digest in closed['input_files_sha256'].items(): inputs.read(path, digest)
    for group in ('projection_sources', 'producer_research_sources'):
        for name, digest in closed[group].items(): inputs.read(args.audit_root / 'Codecs/LPX/research' / name, digest)
    for name, digest in closed['production_sources'].items():
        inputs.read(Path(closed['source_root']) / name, digest)
        inputs.read(ROOT / name, digest)
    item = point['tuples'][0]
    require(item['id'] == 'useful-001' and item['selected_caps'] == [100]
            and item['full_flash_cap'] is None and item['whole_row']['full_flash_bytes'] is None
            and item['whole_row']['automatic_quality_eligible'], 'The selected useful point/cap scope changed')
    require(point['decoded_outputs']['persisted'] is False
            and point['decoded_outputs']['expected_pcm16_path'] is None
            and point['decoded_outputs']['expected_pwm_path'] is None, 'Do not silently substitute decoded references')
    original = inputs.json(point['original_baselines_path'], point['original_baselines_sha256'])
    baseline = next(b for b in original['baselines'] if b['id'] == item['context']['id'])
    require(len(original['baselines']) == 104 and all(item['context'][k] == v for k, v in baseline.items()),
            'The original pre-pilot baseline/target/level changed')
    for arm, folder in point['producer_paths'].items():
        folder = Path(folder); terminal = inputs.json(folder / 'complete-private.json')
        require(terminal['status'] == 'complete', 'A producer is not terminal')
        saved = {n: inputs.json(folder / n, d) for n, d in terminal['output_sha256'].items()}
        require(saved['summary.json']['status'] == 'PASS' and saved['attempt-private.json']['status'] == 'complete'
                and saved['binding-private.json']['source_commit'] == PRODUCTION,
                'A producer/source receipt failed')
        if arm == 'rollback':
            record = next(r for r in saved['results-private.json'] if r['id'] == item['record_id'])
            candidate = next(r for r in record['whole_rows'] if r['id'] == item['candidate_id'])
            chain = next(r for r in record['whole_chains'] if r['id'] == item['candidate_id'])
            require(candidate == item['whole_row'] and record['baseline_id'] == baseline['id']
                    and record['status'] == 'complete' and record['arm'] == 'rollback', 'Useful point differs from closed producer')
            require(len(item['segments']) == len(chain['segments']) == RESETS
                    and all(a[k] == b[k] for a, b in zip(item['segments'], chain['segments']) for k in b),
                    'Candidate ordered descriptors changed')
    require(item['context']['profile'] == 4 and not item['context']['nonspeech']
            and item['context']['samples'] == SAMPLES and baseline['stream_bytes'] == BYTES
            and item['whole_row']['stream_bytes'] == BYTES, 'The fixed full context changed')
    parts = {'baseline': item['baseline_segments'], 'candidate': item['segments']}
    blobs = {role: [inputs.read(p['path'], p['stream_sha256']) for p in values] for role, values in parts.items()}
    for role in parts: geometry(parts[role], blobs[role])
    require(len(item['baseline_segments']) == len(baseline['segments'])
            and all(a[k] == b[k] for a, b in zip(item['baseline_segments'], baseline['segments']) for k in b),
            'The exact original baseline segments changed')
    require(blobs['baseline'] != blobs['candidate'] and all(a[:20] == b[:20] for a, b in zip(blobs['baseline'], blobs['candidate'])),
            'Expected a genuinely new tuple with unchanged original headers')
    target = baseline['prepared_target']
    require(len(inputs.read(target['path'], target['pcm16_sha256'])) == 2 * SAMPLES, 'Prepared target changed')
    return point, item, parts, blobs


def render_native(ops, args, inputs, parts, blobs):
    libraries, bridge = ops.runtime.bridge_native(ROOT, args.native_cases, inputs)
    tools = ops.native.load_tools(ROOT)
    class BoundNative(ops.native.NativeInputs):
        def __init__(self):
            self.tools, self.inputs = tools, inputs
            self.cache, self.counts, self.libraries = {}, Counter(), {}
            for name, path in libraries.items():
                library = ct.CDLL(str(path.resolve()))
                library.lpx_input_decode.argtypes = [ct.POINTER(ct.c_uint8), ct.c_uint16, ct.c_uint32,
                    ct.c_int16, ct.c_uint8, ct.c_uint8, ct.POINTER(ct.c_int16), ct.POINTER(ct.c_uint8),
                    ct.c_uint32, ct.POINTER(ct.c_uint32)]
                library.lpx_input_decode.restype = ct.c_int
                self.libraries[name] = library
    native = BoundNative(); result = {}
    for role in ('baseline', 'candidate'):
        pcm, pwm, used = [], [], []
        for blob, part in zip(blobs[role], parts[role]):
            value = native.reference(blob, 4, part['samples'])
            pcm.append(value['pcm'].astype('<i2').tobytes()); pwm.append(value['pwm'].tobytes()); used.append(value['used'])
        folder = args.output / 'references' / role; folder.mkdir(parents=True)
        for name, raw in (('expected.pcm16le', b''.join(pcm)), ('expected.pwm8', b''.join(pwm))):
            with (folder / name).open('xb') as stream: stream.write(raw)
            inputs.read(folder / name, sha(raw))
        require((folder / 'expected.pcm16le').stat().st_size == 2 * SAMPLES
                and (folder / 'expected.pwm8').stat().st_size == SAMPLES, 'Full native reference length differs')
        result[role] = dict(id=role, segments=parts[role], profile=4, samples=SAMPLES, stream_bytes=BYTES,
            expected_pcm16_path=str(folder / 'expected.pcm16le'), expected_pwm_path=str(folder / 'expected.pwm8'),
            expected_pcm16_sha256=sha(b''.join(pcm)), expected_pwm_sha256=sha(b''.join(pwm)),
            requested_payload_by_reset=used)
    return result, bridge, dict(native.counts)


def prepare(args):
    require(not args.output.exists() and args.output.is_relative_to(ROOT / 'build'), 'Use fresh private preparation output')
    args.output.mkdir(parents=True)
    save(args.output / 'attempt-started-private.json', dict(status='started', target_jobs=0, native_builds=0))
    try:
        inputs = Inputs(); inventory = bind_sources(args.source_commit, inputs)
        point, selected, parts, blobs = select_point(args, inputs)
        ops = operators()
        require(sha(inputs.read(args.native_cases)) == point['native_bridge']['old_native_cases_sha256'], 'Native epoch changed')
        chains, bridge, counts = render_native(ops, args, inputs, parts, blobs)
        observer = inputs.json(args.observer_receipt)
        inputs.read(args.observer, observer['binary_sha256'])
        for name, digest in observer['source_sha256'].items(): inputs.read(name, digest)
        # The exact current observer source must also match the retained build.
        source_hashes = set(observer['source_sha256'].values())
        require(sha((VAL / 'sim_player.c').read_bytes()) in source_hashes, 'Current observer source differs')
        env = ops.bench.environment(ACTIVE, args.avr_bin, True, harness=ops.rom.EXAMPLE / 'player.cpp',
                                    required_symbols=(), retained_symbols=())
        env['settings'] = {**env['settings'], 'queue': 256, 'prefill': 192}
        validation = ops.bench.validation_provenance(args.observer, args.lib, args.wsl)
        inputs.verify(); require(sources() == inventory, 'Preparation source changed')
        handoff = dict(schema='lpx-rollback-current-rom-handoff-private-v1', status='prepared',
            production_commit=PRODUCTION, adapter_commit=args.source_commit, source_inventory=inventory,
            input_files_sha256=inputs.pins, chains=chains, rows=rows(), selected_point=selected,
            native_bridge=bridge, native_counts=counts, build_environment=env, validation=validation,
            avr_bin=str(args.avr_bin), runner=str(args.observer), lib=str(args.lib), wsl=args.wsl,
            input_callback=0, cpu_hz=16000000, audio_hz=8000, queue=256, prefill=192,
            expected_target_rows=4, historical_target_proof_reused=False, native_builds=0, target_jobs=0,
            physical_board_claim=False, c_8khz_sustainability_claim=False)
        save(args.output / 'handoff-private.json', handoff)
        save(args.output / 'complete-private.json', dict(status='complete',
            handoff_sha256=sha((args.output / 'handoff-private.json').read_bytes()), native_builds=0, target_jobs=0))
        print('{"status":"current-source references and four-row handoff prepared","target_jobs":0}', flush=True)
    except Exception as exc:
        save(args.output / 'failure-private.json', dict(status='failed', exception_type=type(exc).__name__, traceback=traceback.format_exc()))
        raise


def context(args):
    raw = args.handoff.read_bytes(); h = json.loads(raw)
    marker = json.loads((args.handoff.parent / 'complete-private.json').read_bytes())
    require(marker['status'] == 'complete' and marker['handoff_sha256'] == sha(raw)
            and h['schema'] == 'lpx-rollback-current-rom-handoff-private-v1'
            and h['status'] == 'prepared' and h['production_commit'] == PRODUCTION and h['rows'] == rows()
            and h['input_callback'] == 0 and h['cpu_hz'] == 16000000 and h['audio_hz'] == 8000
            and h['queue'] == 256 and h['prefill'] == 192, 'Invalid fixed handoff')
    require(sources() == h['source_inventory'], 'Current source/adapter changed')
    for path, digest in h['input_files_sha256'].items(): require(sha(Path(path).read_bytes()) == digest, 'Bound input changed')
    return h, raw, operators()


def reopen(ops, h, row, record):
    chain = h['chains'][row['role']]; folder = Path(record['output'])
    verified = ops.spi.reopen_rom(chain, row, folder, Path(h['avr_bin']), Path(h['runner']), Path(h['lib']), h['wsl'], record)
    require(verified == record['verification'], 'Persisted current-source proof differs')
    cost = verified['cost']; report_ok(verified['report'])
    require(cost['flash_bytes'] == cost['text_bytes'] + cost['data_bytes'] <= 32768
            and cost['static_sram_bytes'] == cost['data_bytes'] + cost['bss_bytes'] <= 2048
            and cost['program_flash_bytes'] == cost['flash_bytes'] - BYTES
            and cost['assembly_enabled'] is True and cost['extra_irq_cycles'] == row['extra_irq_cycles'],
            'Complete image/backend/cost binding failed')
    require(all(not f.startswith('-DLPX4_ENABLE_INPUT_CALLBACK=1') for f in cost['compiler_options']), 'ROM callback setting changed')
    symbols = ops.rom.symbols(folder / 'player.elf', Path(h['avr_bin']))
    table_sizes = []
    for label in ('lpx_voices', 'lpx_sizes'):
        matches = [value for name, value in symbols.items() if re.fullmatch(r'(?:_ZL[0-9]+)?' + label + r'(?:\..*)?', name)]
        require(len(matches) == 1 and matches[0]['size'] == 2 * RESETS, 'Linked reset metadata table changed')
        table_sizes.append(matches[0]['size'])
    return verified, sum(table_sizes)


def measure(args):
    h, raw, ops = context(args)
    require(not args.output.exists() and args.output.is_relative_to(ROOT / 'build'), 'Preserve an existing measurement attempt')
    args.output.mkdir(parents=True)
    save(args.output / 'attempt-private.json', dict(status='started', handoff_sha256=sha(raw), events=[]))
    records, events = [], []
    original_save = ops.rom.save
    ops.rom.save = save  # IO retry only; no source/recipe or simulation cache relaxation.
    try:
        for row in rows():
            require(sources() == h['source_inventory'] and args.handoff.read_bytes() == raw, 'Frozen source/handoff changed')
            chain = h['chains'][row['role']]; folder = args.output / 'images' / row['id']
            require(not folder.exists(), 'Preserve a prior image attempt')
            blobs = [Path(p['path']).read_bytes() for p in chain['segments']]; geometry(chain['segments'], blobs)
            verified = ops.rom.simulate(blobs, folder, Path(h['avr_bin']), Path(h['runner']), source=ACTIVE,
                queue=256, prefill=192, irq=row['extra_irq_cycles'], assembly=True,
                lib=Path(h['lib']), wsl=h['wsl'], expected_pwm=Path(chain['expected_pwm_path']).read_bytes())
            record = normalize(dict(**row, output=str(folder), verification=verified))
            saved = args.output / 'rows' / (row['id'] + '-private.json')
            save(saved, record)
            # Strict checks always see the actual persisted JSON representation.
            persisted = json.loads(saved.read_bytes()); checked, table = reopen(ops, h, row, persisted)
            records.append(dict(**persisted, linked_metadata_bytes=table))
            events.append(dict(id=row['id'], status='passed'))
            save(args.output / 'attempt-private.json', dict(status='running', handoff_sha256=sha(raw), events=events))
            print(json.dumps(dict(status='row-passed', row=row['id'], rows_complete=len(records), expected_rows=4)), flush=True)
        save(args.output / 'results-private.json', dict(status='complete', handoff_sha256=sha(raw), rows=records))
        save(args.output / 'attempt-private.json', dict(status='complete', handoff_sha256=sha(raw), events=events))
    except Exception as exc:
        save(args.output / 'failure-private.json', dict(status='failed', events=events, exception_type=type(exc).__name__, traceback=traceback.format_exc()))
        raise
    finally:
        ops.rom.save = original_save


def aggregate(args):
    h, raw, ops = context(args)
    result = json.loads((args.output / 'results-private.json').read_bytes())
    attempt = json.loads((args.output / 'attempt-private.json').read_bytes())
    require(result['status'] == attempt['status'] == 'complete' and result['handoff_sha256'] == attempt['handoff_sha256'] == sha(raw)
            and attempt['events'] == [dict(id=r['id'], status='passed') for r in rows()]
            and len(result['rows']) == 4, 'The four-row attempt is not terminal')
    public = []
    for row, record in zip(rows(), result['rows']):
        persisted = json.loads((args.output / 'rows' / (row['id'] + '-private.json')).read_bytes())
        require(all(record[k] == v for k, v in persisted.items()), 'Saved row differs')
        verified, table = reopen(ops, h, row, persisted)
        cost = verified['cost']
        public.append(dict(**row, samples=SAMPLES, reset_segments=RESETS, stored_stream_bytes=BYTES,
            full_flash_bytes=cost['flash_bytes'], program_excluding_stream_bytes=cost['program_flash_bytes'],
            linked_metadata_bytes=table, static_sram_bytes=cost['static_sram_bytes'], report=verified['report'],
            physical_pwm_exact=True, passed=True))
    summary = dict(status='complete', rows=4, passed=4, physical_samples=4 * SAMPLES, underruns=0,
        new_fits=0, historical_target_proof_reused=False, physical_board_claim=False, c_8khz_sustainability_claim=False)
    save(args.output / 'summary.json', summary); save(args.output / 'rows.json', public)
    save(args.output / 'artifact-check-private.json', dict(status='passed', handoff_sha256=sha(raw), all_four_current_source_proofs_reopened=True))
    print(json.dumps(summary), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=('prepare', 'measure', 'aggregate'))
    for name in ('selection', 'audit-root', 'native-cases', 'avr-bin', 'observer', 'observer-receipt', 'lib', 'output', 'handoff'):
        p.add_argument('--' + name, type=Path)
    p.add_argument('--source-commit'); p.add_argument('--wsl'); args = p.parse_args()
    for name, value in vars(args).items():
        if isinstance(value, Path): setattr(args, name, value.resolve())
    required = ('selection', 'audit_root', 'native_cases', 'source_commit', 'avr_bin', 'observer', 'observer_receipt', 'lib', 'output') if args.action == 'prepare' else ('handoff', 'output')
    if any(getattr(args, name) is None for name in required): p.error('Missing inputs for the explicit action')
    {'prepare': prepare, 'measure': measure, 'aggregate': aggregate}[args.action](args)


if __name__ == '__main__': main()
