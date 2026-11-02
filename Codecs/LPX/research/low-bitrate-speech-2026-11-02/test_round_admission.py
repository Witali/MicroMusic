"""Crash recovery and duplicate-work accounting, independently of native builds."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import round_admission as admission
from round_admission import RoundAdmission, recover_best
import speech_compact as compact
from standard_metrics import pwm_duties


class ModelReceiver:
    def decode_one_s16(self, blob, n):
        result = compact.decode_model(blob)
        return result if len(result) == n else None

    def decode_one(self, blob, n):
        return pwm_duties(self.decode_one_s16(blob, n))


class RoundJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = compact.pack(9600, 4, [list(range(10))]*30,
                                [(1, 18, 0)]*60, [(0, -8)]*480)[0]
        cls.reference = compact.decode_model(cls.blob)
        parameters = [(1, 18, 0)]*60
        parameters[0] = (2, 18, 0)
        cls.changed = compact.pack(9600, 4, [list(range(10))]*30,
                                   parameters, [(0, -8)]*480)[0]

    def test_duplicate_attempts_are_charged_and_expected_pcm_still_checked(self):
        with tempfile.TemporaryDirectory(dir=admission.ROOT/'build') as folder:
            journal = RoundAdmission(self.reference, self.blob, Path(folder)/'round',
                                     ModelReceiver(), ModelReceiver(), speech=False)
            journal.add(self.blob, self.reference, origin='duplicate', work={'trials': 17})
            incorrect = self.reference.astype(np.int32)+1
            with self.assertRaises(AssertionError):
                journal.add(self.blob, incorrect, origin='incorrect_duplicate')
            blob, _, report = journal.finish()
            self.assertEqual(blob, self.blob)
            self.assertEqual(len(report['candidates']), 1)
            self.assertEqual(len(report['attempts']), 2)
            self.assertEqual(report['actual_work_totals']['trials'], 17)
            self.assertEqual(report['attempts'][1]['duplicate_of'], 0)

    def test_interrupted_multi_file_writes_leave_previous_checkpoint_recoverable(self):
        original_write = admission.atomic_bytes
        for interrupted_name in ('candidate-001.lpx', 'candidate-001-private.json', 'best-private.json'):
            with self.subTest(interrupted_name=interrupted_name):
                with tempfile.TemporaryDirectory(dir=admission.ROOT/'build') as folder:
                    output = Path(folder)/'round'
                    journal = RoundAdmission(self.reference, self.blob, output,
                                             ModelReceiver(), ModelReceiver(), speech=False)

                    def interrupted(path, data):
                        if path.name == interrupted_name:
                            raise OSError('Injected interruption between checkpoint files')
                        original_write(path, data)

                    with patch.object(admission, 'atomic_bytes', side_effect=interrupted):
                        with self.assertRaises(OSError):
                            journal.add(self.changed, origin='new_complete_candidate')
                    # Even a damaged convenience copy cannot replace the
                    # committed immutable stream referenced by best-private.
                    (output/'selected.lpx').write_bytes(b'incomplete convenience copy')
                    recovered, row = recover_best(output)
                    self.assertEqual(recovered, self.blob)
                    self.assertEqual(row['id'], 0)


if __name__ == '__main__':
    unittest.main()
