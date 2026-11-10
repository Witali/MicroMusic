"""Lossless v9 data reduction, all pulse pairs and portable decoder variants."""
import ctypes as ct
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from test_sram512_profile import fixture

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from speech_v9 import repack,pulse_pair,pulse_positions,Bits


def all_pairs():
    w=Bits()
    for fi in range(50):
        if fi:w.put(0,1)
        else:
            w.put(1,1);w.put(0,1)
            for _ in range(10):w.put(1,1);w.put(0,2)
        for half in range(2):
            w.put(23,5);w.put(127,7);w.put(0 if fi&1 else 7,3)
            for si in range(4):
                index=fi*8+half*4+si
                w.put(index,9);w.put(index&15,4);w.put((index>>4)&15,4)
    return struct.pack('<4sBBHIHHHHH',b'L4HY',5,6,8000,16000,8192,11469,320,160,len(w.output))+w.output


class SpeechV9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name);cls.libs={}
        for version,memory,rom,batch in [(5,0,1,1)]+[(9,m,r,b) for m in (0,1) for r in (0,1) for b in (0,1)]:
            path=cls.folder/f'v{version}-{memory}-{rom}-{batch}.so'
            subprocess.run(['g++','-O2','-std=c++11','-shared','-fPIC',
                '-DLPX4_ENABLE_ASM=0','-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                '-DLPX4_COMPACT_ONLY=1','-DLPX4_ENABLE_INPUT_CALLBACK=1',
                f'-DLPX4_COMPACT_VERSION={version}',f'-DLPX4_MEMORY_PROFILE={memory}',
                f'-DLPX4_ROM_POINTER={rom}',f'-DLPX4_BATCHED_REMAINING={batch}',
                '-I'+str(ROOT/'src'),str(ROOT/'src/Lpx4HybridCore.cpp'),
                str(ROOT/'tests/input_callback_native.cpp'),'-o',str(path)],check=True,capture_output=True)
            lib=ct.CDLL(str(path));fn=lib.lpx_input_decode
            fn.argtypes=[ct.POINTER(ct.c_uint8),ct.c_uint16,ct.c_uint32,ct.c_int16,ct.c_uint8,ct.c_uint8,
                ct.POINTER(ct.c_int16),ct.POINTER(ct.c_uint8),ct.c_uint32,ct.POINTER(ct.c_uint32)]
            fn.restype=ct.c_int;cls.libs[version,memory,rom,batch]=lib

    @classmethod
    def tearDownClass(cls):
        cls.libs.clear();cls.temp.cleanup()

    def decode(self,key,blob,domain=0,mode=0):
        n=int.from_bytes(blob[5:7] if blob[:2]==b'L9' else blob[8:12],'little')
        data=(ct.c_uint8*len(blob))(*blob);pcm=(ct.c_int16*(n+1))();pwm=(ct.c_uint8*(n+1))();meta=(ct.c_uint32*8)()
        got=self.libs[key].lpx_input_decode(data,len(blob),len(blob),-1,mode,domain,pcm,pwm,n+1,meta)
        return got,tuple(meta[:5]),bytes(pcm)[:max(got,0)*2] if domain==0 else bytes(pwm)[:max(got,0)]

    def test_all_pair_codes_and_native_samples(self):
        codes=set()
        for first in range(20):
            for second in range(20):
                code=pulse_pair(first,second);codes.add(code)
                self.assertEqual(pulse_positions(code),(first,second))
        self.assertEqual(len(codes),400)
        for code in set(range(512))-codes:
            with self.assertRaises(ValueError):pulse_positions(code)
            bad,_=repack(fixture(6,40,18,'static',False))
            bad=bytearray(bad)
            # 32 spectral bits + 15 nonzero-gain metadata bits precede the pair.
            for bit in range(9):
                at=47+bit;mask=1<<(at&7)
                bad[13+(at>>3)]=(bad[13+(at>>3)]&~mask)|(((code>>bit)&1)<<(at&7))
            with self.assertRaises(ValueError):repack(bad)
            for key in self.libs:
                if key[0]==9:self.assertEqual(self.decode(key,bad)[1][1],3,key)
        old=bytes(all_pairs());new,_=repack(old)
        for domain in (0,1):
            expected=self.decode((5,0,1,1),old,domain)
            self.assertEqual(expected[:2],(16000,(1,0,16000,16000,1)))
            for key in self.libs:
                if key[0]==9:self.assertEqual(self.decode(key,new,domain),expected,key)

    def test_tails_coefficients_sources_and_repacking(self):
        for profile in (4,6):
          for n in (1,19,20,21,39,40,41,159,160,161,319,320,321,641):
            old=fixture(profile,n,145,'changing',True)
            new,stats=repack(old)
            self.assertLessEqual(len(new),len(old)-9)
            self.assertLessEqual(stats['payload_bits'],stats['input_payload_bits'])
            restored,_=repack(new,5);again,_=repack(restored)
            self.assertEqual(again,new)
            for domain in (0,1):
                expected=self.decode((5,0,1,1),old,domain)
                self.assertEqual(expected[:2],(n,(1,0,n,n,1)))
                for key in self.libs:
                    if key[0]==9:
                        for mode in (0,1,2,3,5):
                            self.assertEqual(self.decode(key,new,domain,mode),expected,(key,profile,n,domain,mode))
        for profile in (4,6):
          for extras in (False,True):
           for pre in (0,1,8192,16383,16384):
            for bright in (0,64,11469):
                old=bytearray(fixture(profile,641,18,'clusters',extras))
                struct.pack_into('<HH',old,12,pre,bright);new,_=repack(old)
                self.assertEqual(struct.unpack_from('<HH',new,7),(pre,bright))
                self.assertEqual(self.decode((9,1,1,1),new),self.decode((5,0,1,1),old))
        old=fixture(6,64000,145,'static',False);new,_=repack(old)
        self.assertEqual(self.decode((9,1,1,1),new),self.decode((5,0,1,1),old))

    def test_strict_new_payload_and_metadata_rejections(self):
        good,_=repack(fixture(6,321,18,'changing',True))
        bad=[good[:i] for i in range(len(good))]+[good+b'\0']
        for at,width,value in ((1,1,56),(2,1,15),(3,2,16000),(5,2,0),(5,2,64001),(7,2,16385),(9,2,11470)):
            blob=bytearray(good);blob[at:at+width]=value.to_bytes(width,'little');bad.append(blob)
        for blob in bad:
            with self.assertRaises(ValueError):repack(blob)
        # Correctly declared trailing bytes/padding must still fail at EOF.
        blob=bytearray(good+b'\0');struct.pack_into('<H',blob,11,len(blob)-13)
        with self.assertRaises(ValueError):repack(blob)
        for key in self.libs:
            if key[0]==9:self.assertNotEqual(self.decode(key,blob)[1][1],0,key)

    def test_word_count_preserves_wide_metadata_after_rejected_begin(self):
        old=fixture(6,641,18,'changing',True);new,_=repack(old)
        for count in (0,64001,65535):
            a,b=bytearray(old),bytearray(new)
            struct.pack_into('<I',a,8,count);struct.pack_into('<H',b,5,count)
            expected=self.decode((5,0,1,1),a)
            self.assertEqual(expected[1][2],count)
            for key in self.libs:
                if key[0]==9:self.assertEqual(self.decode(key,b),expected,key)


if __name__=='__main__':unittest.main()
