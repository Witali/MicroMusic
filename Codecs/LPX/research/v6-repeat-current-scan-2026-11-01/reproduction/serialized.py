"""Existing audited serialized operations with explicit forbidden-call guards."""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import hashlib
import importlib.util
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[5]
ACTIVE = ROOT / 'Codecs/LPX/01_ACTIVE_Q0_CODEC'
TOOLS = ACTIVE / 'tools'
PROTOTYPE = ROOT / 'Codecs/LPX/research/v6-scale-repeat-2026-10-28/prototype'
# Existing local dependencies only; no package installation or native build.
for tree in (ROOT.parents[1] / 'build/codec-python', ROOT.parents[1] / 'build/codec-plot'):
    if tree.is_dir():
        sys.path.append(str(tree))
sys.path.insert(0, str(TOOLS))
import speech_compact as compact
import speech_parameter_costs as costs
import speech_parameter_histograms as histograms
from lpx4 import BitWriter


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


converter = module('repeat_current_raw_converter', PROTOTYPE / 'scale_repeat.py')
reference = module('repeat_current_indexed_reference', PROTOTYPE / 'reference.py')
sha = lambda raw: hashlib.sha256(raw).hexdigest()


class ForbiddenOperations:
    """Reject numerical codec work and external/native launches after imports."""
    NAMES = {'decode_model', 'synthesize', 'coefficient_trace', 'encode', 'search',
             'build_library', 'standard_metrics', 'evaluate_quality', 'fit', 'fit_lpc'}

    def __init__(self):
        self.attempts = []
        self.stack = ExitStack()
        self.active = False

    def reject(self, *args, **kwargs):
        self.attempts.append('forbidden-codec-operation')
        raise AssertionError('Synthesis/metrics/fitting/native/target work is forbidden')

    def audit(self, event, args):
        if self.active and event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'ctypes.dlopen'):
            self.attempts.append(event)
            raise AssertionError('External program or native-library load is forbidden')

    def __enter__(self):
        for value in list(sys.modules.values()):
            path = getattr(value, '__file__', None)
            if not path:
                continue
            path = Path(path).resolve()
            if not (path.is_relative_to(TOOLS) or path.is_relative_to(PROTOTYPE)):
                continue
            for name, function in list(vars(value).items()):
                if callable(function) and (name in self.NAMES or getattr(function, '__name__', None) in self.NAMES):
                    self.stack.enter_context(patch.object(value, name, self.reject))
        sys.addaudithook(self.audit)
        self.active = True
        return self

    def __exit__(self, *args):
        self.active = False
        self.stack.close()


def inspect(blob):
    """Counter, raw converter and independent reverse agree without synthesis."""
    info = costs.inspect_stream(blob)
    result = costs.stream_cost(blob, costs.METHODS[0], info)
    converted = converter.from_v5(blob)
    restored = converter.to_v5(converted)
    independent, parameters = reference.restore_v5(converted)
    if restored != blob or independent != blob or parameters != info['params']:
        raise AssertionError('Exact current V5 bytes/raw parameters could not be preserved')
    if len(converted) != result['proposed_file_bytes']:
        raise AssertionError('Audited cost differs from actual in-memory serialized length')
    if converted[:4] != b'L4HY' or converted[4] != 6 or converted[22] != 1:
        raise AssertionError('Unexpected experimental tag/selector')
    if len(converted) != 22 + int.from_bytes(converted[20:22], 'little'):
        raise AssertionError('Experimental payload length differs')
    coded = histograms.parameter_codes(info['params'])
    # An independent integer count, including every stored/unplayed tuple.
    bits = 15 + sum(10 + 1 + (0 if now[0] == old[0] else 5)
                    for old, now in zip(coded, coded[1:]))
    if bits != result['proposed_parameter_bits']:
        raise AssertionError('Independent repeat-mask1 parameter count differs')
    normalized, meta = compact.pack(*compact.unpack(blob)[:7],
        extras=compact.unpack(blob)[7], force_extras=bool(blob[5] & 128))
    canonical = normalized == blob
    if canonical and meta['payload_bits'] != info['current_payload_bits']:
        raise AssertionError('Canonical writer/source bit cursor differs')
    return info, result, dict(complete_byte_roundtrip=True, independent_raw_parameter_roundtrip=True,
        independent_parameter_bits=bits, actual_serialized_size_checked=True,
        existing_v5_writer_byte_exact=canonical,
        noncanonical_source_retained_without_normalizing=not canonical,
        experimental_sha256=sha(converted))


def empty_histogram():
    return {label: dict(tuples=0, first_tuples=0, transitions=0, tuple_repeats=0,
        fields={name: dict(absolute=Counter(), delta=Counter(), repeats=0)
                for name, width in histograms.FIELDS}) for label in ('stored', 'audible')}


def add_histogram(result, info):
    coded = histograms.parameter_codes(info['params'])
    for label, packets in (('stored', coded), ('audible', coded[:info['audible_tuples']])):
        group = result[label]
        group['tuples'] += len(packets)
        group['first_tuples'] += 1
        group['transitions'] += max(0, len(packets) - 1)
        for index, packet in enumerate(packets):
            for i, (field, width) in enumerate(histograms.FIELDS):
                group['fields'][field]['absolute'][packet[i]] += 1
                if index:
                    delta = packet[i] - packets[index - 1][i]
                    group['fields'][field]['delta'][delta] += 1
                    group['fields'][field]['repeats'] += int(delta == 0)
            if index:
                group['tuple_repeats'] += int(packet == packets[index - 1])


def hand_stream(profile, samples=321, scale=0):
    """Hand-authored legal bits, nonminimal Rice and legal zero-amplitude marker."""
    import struct
    writer = BitWriter()
    packets = (samples + 319) // 320
    for frame in range(packets):
        writer.put(1, 1)
        writer.put(0, 1)
        previous = -1
        for value in range(1, 21, 2):
            writer.put(0, 8)
            writer.put(value - previous - 1, 5 if profile == 4 else 6)
            previous = value
        for half in range(2):
            index = 2 * frame + half
            raw_scale = scale if index % 4 < 2 else (scale + 1) % 32
            writer.put(raw_scale, 5)
            writer.put(127 if index & 1 else 0, 7)
            writer.put(0 if index < 2 else 7, 3)
            for chunk in range(4):
                # The existing writer deliberately accepts at most eight bits.
                width = 10 if profile == 4 else 17
                while width:
                    take = min(8, width)
                    writer.put(0, take)
                    width -= take
                marker = frame == half == chunk == 0
                writer.put(int(marker), 1)
                if marker:
                    writer.put(39, 6)
                    writer.put(0, 4)
    writer.aligned()
    payload = writer.get()
    return struct.pack('<4sBBHIHHHHH', b'L4HY', 5, profile | 128, 8000,
                       samples, 0, 0, 320, 160, len(payload)) + payload
