"""Bounded retries preserve atomic JSON output under transient read locks."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import call, patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from benchmark_standards import save


class AtomicBenchmarkSaveTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path=Path(self.temporary.name)/'report.json'
        self.temp=self.path.with_name(self.path.name+'.writing')
        self.old=b'{"previous":true}\n'
        self.path.write_bytes(self.old)
        self.value={'message':'Тихая речь','values':[1,2.5,None]}
        self.expected=(json.dumps(self.value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()

    def test_success_preserves_exact_json_bytes_and_removes_temporary(self):
        with patch('benchmark_standards.time.sleep') as sleep:
            self.assertIsNone(save(self.path,self.value))
        self.assertEqual(self.path.read_bytes(),self.expected)
        self.assertFalse(self.temp.exists());sleep.assert_not_called()

    def test_transient_permission_errors_retry_with_old_destination_intact(self):
        replace=Path.replace;attempts=[]
        def locked_then_replace(source,destination):
            self.assertEqual(source,self.temp);self.assertEqual(destination,self.path)
            self.assertEqual(source.read_bytes(),self.expected)
            self.assertEqual(self.path.read_bytes(),self.old)
            attempts.append(1)
            if len(attempts)<3:raise PermissionError(13,'Transient read lock')
            return replace(source,destination)
        with patch.object(Path,'replace',autospec=True,side_effect=locked_then_replace), \
             patch('benchmark_standards.time.sleep') as sleep:
            save(self.path,self.value)
        self.assertEqual(len(attempts),3)
        self.assertEqual(sleep.call_args_list,[call(.01),call(.02)])
        self.assertEqual(self.path.read_bytes(),self.expected);self.assertFalse(self.temp.exists())

    def test_sixth_attempt_can_succeed_after_all_bounded_delays(self):
        replace=Path.replace;attempts=[]
        def locked_then_replace(source,destination):
            attempts.append(1)
            if len(attempts)<6:raise PermissionError(13,'Transient read lock')
            return replace(source,destination)
        with patch.object(Path,'replace',autospec=True,side_effect=locked_then_replace), \
             patch('benchmark_standards.time.sleep') as sleep:
            save(self.path,self.value)
        self.assertEqual(len(attempts),6)
        self.assertEqual(sleep.call_args_list,[call(.01),call(.02),call(.04),call(.08),call(.16)])
        self.assertEqual(self.path.read_bytes(),self.expected)

    def test_permanent_permission_error_propagates_and_preserves_both_files(self):
        error=PermissionError(13,'Permanent read lock')
        with patch.object(Path,'replace',side_effect=error) as replace, \
             patch('benchmark_standards.time.sleep') as sleep:
            with self.assertRaises(PermissionError) as raised:save(self.path,self.value)
        self.assertIs(raised.exception,error);self.assertEqual(replace.call_count,6)
        self.assertEqual(sleep.call_args_list,[call(.01),call(.02),call(.04),call(.08),call(.16)])
        self.assertEqual(self.path.read_bytes(),self.old);self.assertEqual(self.temp.read_bytes(),self.expected)

    def test_unrelated_replace_error_is_not_retried(self):
        error=OSError(28,'Unrelated filesystem error')
        with patch.object(Path,'replace',side_effect=error) as replace, \
             patch('benchmark_standards.time.sleep') as sleep:
            with self.assertRaises(OSError) as raised:save(self.path,self.value)
        self.assertIs(raised.exception,error);replace.assert_called_once();sleep.assert_not_called()
        self.assertEqual(self.path.read_bytes(),self.old);self.assertEqual(self.temp.read_bytes(),self.expected)

    def test_permission_error_while_writing_is_not_retried(self):
        with patch.object(Path,'write_bytes',side_effect=PermissionError(13,'Write denied')), \
             patch.object(Path,'replace') as replace,patch('benchmark_standards.time.sleep') as sleep:
            with self.assertRaises(PermissionError):save(self.path,self.value)
        replace.assert_not_called();sleep.assert_not_called()
        self.assertEqual(self.path.read_bytes(),self.old)

    def test_nonfinite_json_still_fails_before_replacing_destination(self):
        with patch.object(Path,'replace') as replace,patch('benchmark_standards.time.sleep') as sleep:
            with self.assertRaises(ValueError):save(self.path,{'value':float('nan')})
        replace.assert_not_called();sleep.assert_not_called()
        self.assertEqual(self.path.read_bytes(),self.old)


if __name__=='__main__':unittest.main()
