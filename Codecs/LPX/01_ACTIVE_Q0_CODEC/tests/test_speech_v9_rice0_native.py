"""Experimental Rice0 reader against the unchanged production C oracle.

The experiment builds private source copies. It never enables the new syntax
in production firmware. Requires g++, ctypes and the Python standard library.
"""
import ctypes as ct
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_speech_v9_rice0 import ROOT,fixture,_fixture
from speech_v9_rice0_experiment import repack

spec=importlib.util.spec_from_file_location('rice0_reader',ROOT.parent/'research/v9-rice0-2026-11-10/reader.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)


class Rice0NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();folder=Path(cls.temp.name)
        private=reader.make_reader_tree(folder/'src');cls.libs={}
        matrix=[('old',ROOT/'src',0,1,1)]+[
            ((memory,rom,batch),private,memory,rom,batch)
            for memory in (0,1) for rom in (0,1) for batch in (0,1)]
        for index,(key,source,memory,rom,batch) in enumerate(matrix):
            library=folder/('reader-%d.so'%index)
            subprocess.run(['g++','-O2','-std=c++11','-shared','-fPIC',
                '-DLPX4_ENABLE_ASM=0','-DLPX4_COMPACT_ONLY=1',
                '-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                '-DLPX4_ENABLE_INPUT_CALLBACK=1','-DLPX4_COMPACT_VERSION=9',
                f'-DLPX4_MEMORY_PROFILE={memory}',f'-DLPX4_ROM_POINTER={rom}',
                f'-DLPX4_BATCHED_REMAINING={batch}','-I'+str(source),
                str(source/'Lpx4HybridCore.cpp'),str(ROOT/'tests/input_callback_native.cpp'),
                '-o',str(library)],check=True,capture_output=True)
            lib=ct.CDLL(str(library));fn=lib.lpx_input_decode
            fn.argtypes=[ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint32,ct.c_int16,
                ct.c_uint8,ct.c_uint8,ct.POINTER(ct.c_int16),ct.POINTER(ct.c_uint8),
                ct.c_uint32,ct.POINTER(ct.c_uint32)]
            fn.restype=ct.c_int;cls.libs[key]=lib

    @classmethod
    def tearDownClass(cls):
        cls.libs.clear();cls.temp.cleanup()

    def decode(self,key,blob,domain=0,mode=0,available=None):
        n=int.from_bytes(blob[5:7],'little')
        data=(ct.c_uint8*len(blob))(*blob);pcm=(ct.c_int16*(n+1))()
        pwm=(ct.c_uint8*(n+1))();meta=(ct.c_uint32*8)()
        got=self.libs[key].lpx_input_decode(data,len(blob),len(blob) if available is None else available,
            -1,mode,domain,pcm,pwm,n+1,meta)
        self.assertLessEqual(meta[6],len(blob))
        return got,tuple(meta[:5]),bytes(pcm)[:got*2] if domain==0 else bytes(pwm)[:got]

    def test_profiles_tails_memory_backends_and_input_switching(self):
        selected_count=0
        counts=(1,19,20,39,40,79,80,81,159,160,319,320,321,641,64000)
        for profile,extras in ((4,False),(4,True),(6,False),(6,True),(15,False)):
            for n in counts:
                original=fixture(profile,n,extras=extras);selected,_=repack(original,optimize_rice0=True)
                selected_count+=bool(selected[2]&64)
                self.assertLessEqual(len(selected),len(original))
                for domain in (0,1):
                    expected=self.decode('old',original,domain)
                    self.assertEqual(expected[:2],(n,(1,0,n,n,1)))
                    for key in self.libs:
                        if key=='old':continue
                        for mode in (0,1,2,3,5):
                            self.assertEqual(self.decode(key,selected,domain,mode),expected,(key,profile,n,domain,mode))
        self.assertGreater(selected_count,0)

    def test_zero_deltas_signed_escape_and_redundant_p4_flag(self):
        for profile in (4,6,15):
            for style in ('constant','negative','escape','growth'):
                old=_fixture(profile,12800,style,False)
                new=bytearray(_fixture(profile,12800,style,False,delta_k0=True,force_delta=True))
                if profile==4:new[2]|=64
                for domain in (0,1):
                    expected=self.decode('old',old,domain)
                    for key in self.libs:
                        if key!='old':self.assertEqual(self.decode(key,new,domain,1),expected,(key,profile,style))

    def test_corrupt_tail_and_callback_eof_fail(self):
        original=fixture(15,641);good,_=repack(original,optimize_rice0=True)
        self.assertTrue(good[2]&64)
        for key in self.libs:
            if key=='old':continue
            for available in range(len(good)):
                self.assertNotEqual(self.decode(key,good,mode=1,available=available)[1][1],0,(key,available))
            # Keep the complete-file length internally consistent, but append
            # an unplayed byte. Both ROM and callback EOF must reject it.
            bad=bytearray(good+b'\0');bad[11:13]=(len(bad)-13).to_bytes(2,'little')
            for mode in (0,1):self.assertNotEqual(self.decode(key,bad,mode=mode)[1][1],0,(key,mode))


if __name__=='__main__':unittest.main()
