"""Pure bit contracts; no fitted source, waveform, native build or simulation."""
from pathlib import Path
import subprocess
import unittest

from serialized import ForbiddenOperations, compact, costs, hand_stream, inspect, reference, converter


class SerializedContracts(unittest.TestCase):
    def test_all_raw_scales_tails_and_noncanonical_spans(self):
        with ForbiddenOperations() as guard:
            for profile in (4, 6):
                for scale in range(32):
                    blob = hand_stream(profile, 321, scale)
                    info, cost, proof = inspect(blob)
                    self.assertEqual(info['stored_tuples'], 4)
                    self.assertEqual(info['unplayed_stored_tuples'], 1)
                    self.assertEqual([p[0] for p in info['params']], [scale, scale, (scale + 1) % 32, (scale + 1) % 32])
                    self.assertEqual(cost['parameter_detail']['fields']['scale']['repeats'], 2)
                    self.assertTrue(proof['noncanonical_source_retained_without_normalizing'])
            self.assertEqual(guard.attempts, [])

    def test_boundary_lengths_forced_empty_extras_and_unused_lag(self):
        with ForbiddenOperations() as guard:
            for profile in (4, 6):
                for n in (1, 159, 160, 161, 319, 320, 321, 641):
                    info, cost, proof = inspect(hand_stream(profile, n, 5))
                    self.assertEqual(info['source_extra_value_bits'], 10)
                    self.assertEqual(info['params'][0][1:], (18, 0))
                    self.assertEqual(info['params'][1][1:], (145, 0))
                    self.assertEqual(cost['additional_selector_bytes'], 1)
                    self.assertEqual(cost['proposed_padding_bits'], (-cost['proposed_payload_bits']) % 8)
            self.assertEqual(guard.attempts, [])

    def test_selector_truncation_and_inspection_identity(self):
        with ForbiddenOperations():
            blob = hand_stream(4)
            info = costs.inspect_stream(blob)
            with self.assertRaises(ValueError): costs.stream_cost(hand_stream(6), costs.METHODS[0], info)
            encoded = bytearray(converter.from_v5(blob)); encoded[22] = 2
            with self.assertRaises(ValueError): reference.restore_v5(encoded)
            with self.assertRaises(ValueError): converter.to_v5(encoded)
            with self.assertRaises((ValueError, EOFError, IndexError)): inspect(blob[:-1])

    def test_numerical_and_external_operations_rejected(self):
        with ForbiddenOperations() as guard:
            with self.assertRaises(AssertionError): compact.decode_model(hand_stream(4))
            with self.assertRaises(AssertionError): subprocess.run(['forbidden-study-command'])
            self.assertEqual(len(guard.attempts), 2)


if __name__ == '__main__': unittest.main()
