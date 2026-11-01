import ctypes as ct
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np

import speech_compact as compact
from standard_metrics import pwm_duties
from test_speech_v4 import fixture

ROOT = Path(__file__).resolve().parents[1]


class InputCallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix='lpx-input-callback-')
        cls.libraries = {}
        for only, cursor, enabled in ((1, 1, 0), (1, 1, 1), (1, 0, 1), (0, 1, 1), (0, 0, 1)):
            path = Path(cls.folder.name)/('input-%d-%d-%d.so' % (only,cursor,enabled))
            command = [shutil.which('g++'), '-O3', '-shared', '-fPIC', '-std=c++11',
                '-DLPX4_ENABLE_SPEECH=1', '-DLPX4_ENABLE_SPEECH_COMPACT=1',
                '-DLPX4_COMPACT_ONLY=%d' % only, '-DLPX4_ROM_POINTER=%d' % cursor,
                '-DLPX4_ENABLE_INPUT_CALLBACK=%d' % enabled, '-DLPX4_ENABLE_ASM=0',
                '-I'+str(ROOT/'src'), str(ROOT/'src/Lpx4HybridCore.cpp'),
                str(ROOT/'src/native_batch_decoder.cpp'),
                str(ROOT/'tests/input_callback_native.cpp'), '-o', str(path)]
            subprocess.run(command, check=True, capture_output=True)
            library = ct.CDLL(str(path))
            library.lpx_input_object_size.restype = ct.c_uint32
            library.lpx_input_decode.argtypes = [ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint32,
                ct.c_int16,ct.c_uint8,ct.c_uint8,ct.POINTER(ct.c_int16),ct.POINTER(ct.c_uint8),
                ct.c_uint32,ct.POINTER(ct.c_uint32)]
            library.lpx_input_decode.restype = ct.c_int
            cls.libraries[only,cursor,enabled] = library

    @classmethod
    def tearDownClass(cls):
        if os.name=='nt':
            import _ctypes
            for library in cls.libraries.values():
                _ctypes.FreeLibrary(library._handle)
        cls.libraries.clear()
        cls.folder.cleanup()

    def decode(self, library, blob, n, *, mode=1, domain=0, available=None, failure=-1, size=None):
        data = np.frombuffer(blob, np.uint8)
        pcm, pwm, meta = np.empty(n+1,np.int16), np.empty(n+1,np.uint8), np.zeros(8,np.uint32)
        got = library.lpx_input_decode(data.ctypes.data_as(ct.POINTER(ct.c_uint8)),
            len(blob) if size is None else size, len(blob) if available is None else available,
            failure, mode, domain, pcm.ctypes.data_as(ct.POINTER(ct.c_int16)),
            pwm.ctypes.data_as(ct.POINTER(ct.c_uint8)),n+1,meta.ctypes.data_as(ct.POINTER(ct.c_uint32)))
        return (pcm if domain==0 else pwm)[:max(0,got)].copy(), meta

    def test_callback_and_rom_match_both_profiles_tails_and_cursor_modes(self):
        for profile in (4,6):
            for n in (1,19,20,39,40,159,160,319,320,321,641,64000):
                blob = compact.repack(fixture(profile,n),extras=[(i%40,(-8 if i&1 else 7))
                    for i in range(((n+319)//320)*8)])[0]
                expected = compact.decode_model(blob)
                for key, library in self.libraries.items():
                    for domain, target in ((0,expected),(1,pwm_duties(expected))):
                        actual, meta = self.decode(library,blob,n,mode=1 if key[2] else 0,domain=domain)
                        np.testing.assert_array_equal(actual,target,err_msg=str((key,profile,n,domain)))
                        self.assertEqual(tuple(meta[:5]),(1,0,n,n,1))
                        if key[2]:
                            self.assertEqual(meta[5],meta[6])
                            self.assertGreaterEqual(meta[6],22)
                            self.assertLessEqual(meta[6],len(blob))

    def test_source_switching_clears_old_reader_and_resets_parser(self):
        blob = compact.repack(fixture(6,641))[0]
        expected = compact.decode_model(blob)
        for key, library in self.libraries.items():
            if not key[2]: continue
            for mode in (2,3,5):
                actual, meta = self.decode(library,blob,641,mode=mode)
                np.testing.assert_array_equal(actual,expected)
                self.assertEqual(tuple(meta[:5]),(1,0,641,641,1))
                if mode in (2,5): self.assertEqual(meta[5],meta[7])

    def test_null_and_short_declared_inputs_do_not_call_reader(self):
        blob = compact.repack(fixture(4,641))[0]
        for key, library in self.libraries.items():
            if not key[2]: continue
            for settings in (dict(mode=4),dict(size=19),dict(size=0)):
                actual, meta = self.decode(library,blob,641,**settings)
                self.assertEqual(len(actual),0)
                self.assertEqual(meta[0],0)
                self.assertNotEqual(meta[1],0)
                self.assertEqual(meta[5],0)

    def test_physical_truncation_and_invalid_reader_values_stop_without_overread(self):
        blob = compact.repack(fixture(6,641))[0]
        for key, library in self.libraries.items():
            if not key[2]: continue
            _, complete = self.decode(library,blob,641)
            used = int(complete[6])
            for available in (0,3,21,used-1):
                for failure in (-1,-2,256):
                    actual, meta = self.decode(library,blob,641,available=available,failure=failure)
                    self.assertLess(len(actual),641)
                    self.assertNotEqual(meta[1],0)
                    self.assertLessEqual(meta[5],available+1)
                    self.assertEqual(meta[6],available)

    def test_declared_span_and_trailing_bytes_follow_rom_errors(self):
        original = compact.repack(fixture(4,641))[0]
        trailing = bytearray(original+b'\0')
        trailing[20:22] = (len(trailing)-22).to_bytes(2,'little')
        for key, library in self.libraries.items():
            if not key[2]: continue
            for blob,size in ((original,22),(bytes(trailing),len(trailing))):
                rom, rom_meta = self.decode(library,blob,641,mode=0,size=size)
                actual, meta = self.decode(library,blob,641,size=size)
                np.testing.assert_array_equal(actual,rom)
                np.testing.assert_array_equal(meta[:5],rom_meta[:5])
                if size==22: self.assertNotEqual(meta[1],0)
                self.assertLessEqual(meta[5],size)

    def test_unused_final_packet_tail_is_not_read(self):
        # A short final frame stores a complete packet. ROM decoding stops at
        # the declared sample count; the sequential source must do the same.
        blob = compact.repack(fixture(4,1))[0]
        for key, library in self.libraries.items():
            if not key[2]: continue
            expected, complete = self.decode(library,blob,1)
            used = int(complete[6])
            self.assertLess(used,len(blob))
            actual, meta = self.decode(library,blob,1,available=used)
            np.testing.assert_array_equal(actual,expected)
            np.testing.assert_array_equal(meta,complete)

    def test_common_build_keeps_legacy_v4_through_same_input_api(self):
        for cursor in (0,1):
            library = self.libraries[0,cursor,1]
            for profile in (4,6):
                blob = fixture(profile,641)
                rom, before = self.decode(library,blob,641,mode=0)
                actual, after = self.decode(library,blob,641)
                np.testing.assert_array_equal(actual,rom)
                np.testing.assert_array_equal(after[:5],before[:5])
                self.assertEqual(after[1],0)

    def test_callback_state_is_absent_in_default_layout(self):
        base = self.libraries[1,1,0].lpx_input_object_size()
        enabled = self.libraries[1,1,1].lpx_input_object_size()
        self.assertGreaterEqual(enabled-base,ct.sizeof(ct.c_void_p)*2)


if __name__=='__main__':
    unittest.main()
