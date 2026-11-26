"""Deterministic synthetic four-pulse validation; no speech corpus execution."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
import sys
import time
import unittest

parser = argparse.ArgumentParser()
parser.add_argument('--packages', type=Path)
options, remaining = parser.parse_known_args()
if options.packages:
    sys.path.insert(0, str(options.packages.resolve()))
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exhaustive as e
from native_receiver import NativeReceiver, OUTPUT
import numpy as np
import speech_sparse80 as sparse
from lpx4 import BitWriter
from standard_metrics import pwm_duties


def fixture(n, *, pre=8192, bright=4096, clipping=False):
    frames = (n + 319) // 320
    spectra = [[3 + 5 * j + f % 2 for j in range(10)] for f in range(frames)]
    params = [((31 if clipping else 13 + f % 3), (18, 37, 145)[f % 3], (0, 6, 14)[f % 3])
              for f in range(frames)]
    pulses = [(sparse.POSITIONS[(i * 13) % 64], -8 if i % 2 else 7) for i in range(frames * 4)]
    return sparse.pack(n, spectra, params, pulses, pre, bright)


def nonminimal_spectra(blob):
    """Force legal raw-escape absolute spectra even when bounded Rice is shorter."""
    n, spectra, parameters, pulses, pre, bright = sparse.unpack(blob)
    writer = BitWriter()
    for f, vec in enumerate(spectra):
        writer.put(1, 1)
        writer.put(0, 1)
        gaps = [vec[0]] + [b - a - 1 for a, b in zip(vec, vec[1:])]
        for value in gaps:
            writer.put(0, 8)
            writer.put(value, 6)
        scale, lag, gain = parameters[f]
        writer.put(scale, 5)
        writer.put(lag - 18, 7)
        writer.put(gain // 2, 3)
        for position, amplitude in pulses[f * 4:f * 4 + 4]:
            writer.put(sparse.POSITIONS.index(position), 6)
            writer.put(int(amplitude > 0), 1)
    writer.aligned()
    payload = writer.get()
    return blob[:20] + struct.pack('<H', len(payload)) + payload


def missed_leaf_fixture():
    # Seed0 is an intentionally adversarial synthetic temporal splice, not a
    # speech-like tuning sample. Its first320 reference samples prefer the
    # incumbent; its unchanged tail prefers another actual carried-state trace.
    rng = np.random.default_rng(0)
    n = 1281
    frames = (n + 319) // 320
    spectra = [[3 + 5 * j + f % 2 for j in range(10)] for f in range(frames)]
    params = [(15, 18, 14)] * frames
    pulses = [(sparse.POSITIONS[int(rng.integers(64))], 7 if int(rng.integers(2)) else -8)
              for _ in range(frames * 4)]
    blob = sparse.pack(n, spectra, params, pulses, 15564, 4096)
    context = e.Context(blob)
    alternate = tuple(int(rng.integers(128)) for _ in range(4))
    target = context.render(0, alternate)
    target[:320] = context.pcm[:320]
    return blob, target


class Mechanism(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.started = time.perf_counter()
        cls.receivers = [NativeReceiver('common'), NativeReceiver('v5-only')]
        cls.receiver = staticmethod(e.bridge_receiver(*cls.receivers))
        cls.report = {}
        cls.frozen = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                      for name in ('exhaustive.py', 'test_mechanism.py', 'MECHANISM_PROTOCOL.md')}

    @classmethod
    def tearDownClass(cls):
        for receiver in cls.receivers:
            receiver.close()
            if receiver.process.returncode != 0:
                raise AssertionError('Native reference receiver did not close cleanly')
        after = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in cls.frozen}
        if cls.frozen != after:
            raise AssertionError('Mechanism source changed during validation')
        cls.report.update(schema='lpx-sparse2-frozen-four-synthetic-v1', source_hashes=cls.frozen,
                          interpreter=sys.version.split()[0], numpy=np.__version__,
                          seconds=time.perf_counter() - cls.started,
                          native_requests={r.kind: r.calls for r in cls.receivers},
                          receiver_kind='Existing v8-to-v5/P6 bridge; common and v5-only fixed C',
                          scope='Synthetic mechanism validation only; no speech or audible-quality claim')
        (OUTPUT / 'mechanism-tests.json').write_text(json.dumps(cls.report, indent=2) + '\n', encoding='utf-8')

    def test_exhaustive_missed_leaf_uses_same_frozen_pools(self):
        blob, target = missed_leaf_fixture()
        result = e.search(target, blob, self.receiver)
        frame = next(region for region in result.regions if region.frame == 0)
        self.assertEqual([pool.symbols for pool in frame.pools],
                         [(118, 116, 119), (32, 19, 33), (19, 27, 18), (4, 6, 5)])
        self.assertEqual(frame.exhaustive.symbols, (116, 33, 18, 4))
        self.assertEqual(frame.exhaustive.pcm_sse, 117833156)
        for width, control in frame.controls.items():
            self.assertEqual(control.symbols, (118, 32, 19, 4))
            self.assertEqual(control.pcm_sse, 399466972)
            self.assertLess(frame.exhaustive.pcm_sse, control.pcm_sse)
            self.assertNotIn(frame.exhaustive.symbols, frame.surviving_symbols[width])
        self.assertEqual(result.counters['leaves'], 324)
        self.assertEqual(result.counters['symbol_screens'], 2048)
        self.assertLessEqual(len(result.shortlist), 12)
        self.assertTrue(all(len(values) <= 4 for values in result.control_shortlists.values()))
        self.assertEqual(len({c.blob for c in result.shortlist}), len(result.shortlist))
        context = e.Context(blob)
        for pool in frame.pools:
            replay = e.freeze_pool(context, target, pool.packet)
            self.assertEqual(replay, pool)
            self.assertEqual(len(pool.symbols), 3)
            self.assertEqual(pool.symbols[0], context.layout.symbols[pool.packet])
            self.assertIn(pool.immediate_winner, pool.symbols)
            self.assertIn(pool.tail_winner, pool.symbols)
        # Native verification is mandatory for every UNIQUE full leaf, not just
        # the winner. Repeated baseline leaves are explicitly counted separately.
        self.assertEqual(result.counters['full_model_checks'], 325)
        self.assertEqual(result.counters['native_oracle_calls'], 321)
        self.report['missed_leaf'] = dict(frame=0, pools=[list(p.symbols) for p in frame.pools],
            exhaustive_symbols=list(frame.exhaustive.symbols), exhaustive_pcm_sse=frame.exhaustive.pcm_sse,
            controls={str(w): dict(symbols=list(c.symbols), pcm_sse=c.pcm_sse)
                      for w, c in frame.controls.items()}, counters=result.counters,
            all_full_leaf_model_native_pcm_pwm_exact=True,
            target_recipe='Seed0 synthetic decoder trace, first320 samples replaced by incumbent trace')

    def test_original_nonminimal_bytes_partial_packet_and_native_suffix(self):
        original = fixture(641, clipping=True)
        blob = nonminimal_spectra(original)
        self.assertGreater(len(blob), len(original))
        self.assertEqual(sparse.unpack(blob), sparse.unpack(original))
        context = e.Context(blob)
        target = context.pcm.copy()
        result = e.search(target, blob, self.receiver)
        self.assertEqual(result.baseline.blob, blob)
        self.assertEqual(result.counters['leaves'], 162)
        layout = e.parse_layout(blob)
        editable = set()
        for packet in range(8):
            editable.update(range(layout.pulse_offsets[packet], layout.pulse_offsets[packet] + 7))
        for region in result.regions:
            for leaf in region.leaves:
                self.assertEqual(len(leaf.blob), len(blob))
                fields = sparse.unpack(leaf.blob)
                self.assertEqual(fields[:3], sparse.unpack(blob)[:3])
                self.assertEqual(fields[4:], sparse.unpack(blob)[4:])
                self.assertEqual(fields[3][8:], sparse.unpack(blob)[3][8:])
                for at, (a, b) in enumerate(zip(blob, leaf.blob)):
                    for bit in range(8):
                        if (a ^ b) & (1 << bit):
                            self.assertIn(at * 8 + bit, editable)
                # Unchanged prefix must carry its actual original state, and
                # the final one-sample partial frame remains synthesized.
                np.testing.assert_array_equal(leaf.pcm[:region.frame * 320],
                                               context.pcm[:region.frame * 320])
                self.assertEqual(len(leaf.pcm), 641)
        self.assertNotEqual(result.raw.blob, blob)  # Preserve rejected raw changes.
        self.assertGreaterEqual(result.raw.pcm_sse, result.baseline.pcm_sse)
        with self.assertRaises(ValueError):
            e.patch_symbols(blob, layout, {8: 0})
        self.report['original_bytes'] = dict(nonminimal_spectra=True, samples=641,
            original_bytes=len(blob), all_nonpulse_and_tail_bits_exact=True,
            partial_frame_edit_rejected=True, raw_changed_retained=True, counters=result.counters)

    def test_partial_only_streams_and_fail_closed_oracle(self):
        cases = 0
        for n in (1, 79, 80, 81, 319):
            blob = fixture(n)
            context = e.Context(blob)
            result = e.search(context.pcm, blob, self.receiver)
            self.assertEqual(result.regions, [])
            self.assertEqual(result.shortlist, [])
            self.assertEqual(result.raw.blob, blob)
            self.assertEqual(result.counters['leaves'], 0)
            cases += 1
        blob = fixture(321)
        context = e.Context(blob)
        with self.assertRaises(ValueError):
            e.search(context.pcm.astype(float), blob, self.receiver)
        with self.assertRaises(AssertionError):
            e.search(context.pcm, blob,
                     lambda _: (context.pcm.copy(), np.zeros(321, np.uint8)))
        with self.assertRaises(ValueError):
            e.parse_layout(blob[:-1])
        self.report['partial_only'] = dict(cases=cases, no_partial_frame_edits=True,
                                           invalid_reference_and_oracle_rejected=True)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
