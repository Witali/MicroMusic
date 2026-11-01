"""Pure contracts for bounded replacement and exact recovery-prefix scope."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recover_player import prefix_keys, replace_with_retry, write_once


def windows_error(code):
    value = PermissionError('synthetic replacement failure')
    value.winerror = code
    return value


class RecoveryContracts(unittest.TestCase):
    def test_only_recognized_windows_replace_errors_retry(self):
        temporary, target = Mock(), Mock()
        temporary.replace.side_effect = [windows_error(5), windows_error(32), None]
        observed = []
        with patch('recover_player.time.sleep') as sleep:
            replace_with_retry(temporary, target, lambda error, attempt: observed.append((error, attempt)))
        self.assertEqual(temporary.replace.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertEqual(observed, [(5, 1), (32, 2)])

    def test_other_errors_propagate_immediately(self):
        for error in (PermissionError('synthetic non-Windows failure'), windows_error(87), FileNotFoundError()):
            temporary = Mock()
            temporary.replace.side_effect = error
            with self.subTest(kind=type(error).__name__), patch('recover_player.time.sleep') as sleep:
                with self.assertRaises(type(error)):
                    replace_with_retry(temporary, Mock())
                self.assertEqual(temporary.replace.call_count, 1)
                sleep.assert_not_called()

    def test_exhaustion_is_bounded_and_preserves_temporary_bytes(self):
        with tempfile.TemporaryDirectory(prefix='lpx-recovery-contract-') as folder:
            path = Path(folder)/'receipt.json'
            temporary = path.with_suffix('.writing')
            temporary.write_bytes(b'complete pending bytes')
            with patch.object(Path, 'replace', side_effect=windows_error(5)) as replace, patch('recover_player.time.sleep'):
                with self.assertRaises(PermissionError):
                    replace_with_retry(temporary, path)
            self.assertEqual(replace.call_count, 6)
            self.assertEqual(temporary.read_bytes(), b'complete pending bytes')
            self.assertFalse(path.exists())

    def test_existing_target_and_incomplete_write_are_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='lpx-recovery-contract-') as folder:
            path = Path(folder)/'receipt.json'
            path.write_bytes(b'original receipt')
            with self.assertRaises(ValueError): write_once(path, {'new': True})
            self.assertEqual(path.read_bytes(), b'original receipt')
            other = Path(folder)/'other.json'
            other.with_suffix('.writing').write_bytes(b'preserved incomplete write')
            with self.assertRaises(ValueError): write_once(other, {'new': True})
            self.assertEqual(other.with_suffix('.writing').read_bytes(), b'preserved incomplete write')

    def test_exact_prefix_leaves_only_original_suffix(self):
        expected = [('chain-%d' % i, irq) for i in range(3) for irq in (0, 100)]
        rows = [dict(chain=c, extra_irq_cycles=irq, passed=True, verification={'proof': True})
                for c, irq in expected[:3]]
        self.assertEqual(prefix_keys(rows, expected), expected[3:])
        for wrong in ([rows[1], rows[0]], [rows[0], rows[0]],
                      [dict(rows[0], passed=False)], [dict(rows[0], verification=None)]):
            with self.assertRaises(ValueError): prefix_keys(wrong, expected)
        complete = [dict(chain=c, extra_irq_cycles=irq, passed=True, verification=True) for c, irq in expected]
        with self.assertRaises(ValueError): prefix_keys(complete, expected)


if __name__ == '__main__':
    unittest.main()
