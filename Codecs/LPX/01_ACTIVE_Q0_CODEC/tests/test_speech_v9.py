"""Lossless v9 data reduction, all pulse pairs and portable decoder variants."""
import ctypes as ct
import hashlib
import json
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


def sparse_fixture(n,style='changing',pre=8192,bright=11469,lag=145):
    """Independent v8 sparse80 writer plus its ordinary v5/P6 expansion."""
    writers=[Bits(),Bits()]
    def rice(w,z,k,width):
        high=z>>k
        if high>=8:w.put(0,8);w.put(z,width)
        else:w.put(0,high);w.put(1,1);w.put(z&((1<<k)-1),k)
    previous=None
    for fi in range((n+319)//320):
        vec=list(range(0 if fi%2==0 else 54,10 if fi%2==0 else 64)) if style=='clusters' else [3+5*i+(fi%2 if style=='changing' else 0) for i in range(10)]
        for w in writers:
            if vec==previous:w.put(0,1)
            else:
                delta=previous is not None and style=='changing'
                w.put(1,1);w.put(int(delta),1)
                for i,value in enumerate(vec):
                    d=value-previous[i] if delta else value-(vec[i-1]+1 if i else 0)
                    z=(d*2 if d>=0 else -d*2-1) if delta else d
                    rice(w,z,1 if delta else 2,7 if delta else 6)
        previous=vec
        scale=24+fi%8;gain=(fi%8)*2
        expanded=[(0,0)]*16;raw=[]
        for group in range(4):
            index=fi*4+group;code=(index*13)%64;amp=-8 if (index//64)%2 else 7
            raw.append(code|(64 if amp>0 else 0))
            position=code+((code+2)>>2)
            expanded[group*4+position//20]=(position%20,amp)
        w=writers[0];w.put(scale,5);w.put(lag-18,7);w.put(gain//2,3)
        for value in raw:w.put(value,7)
        w=writers[1]
        for half in range(2):
            w.put(scale,5);w.put(lag-18,7);w.put(gain//2,3)
            for group in range(4):
                (a,x),(b,y)=expanded[half*8+group*2:half*8+group*2+2]
                w.put(a+20*b,9);w.put(x&15,4);w.put(y&15,4)
    def wrap(w,version,profile,block):
        return struct.pack('<4sBBHIHHHHH',b'L4HY',version,profile,8000,n,pre,bright,320,block,len(w.output))+w.output
    return wrap(writers[0],8,15,320),wrap(writers[1],5,6,160)


class SpeechV9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name);cls.libs={}
        for version,memory,rom,batch in [(5,0,1,1),(8,0,1,1)]+[(9,m,r,b) for m in (0,1) for r in (0,1) for b in (0,1)]:
            path=cls.folder/f'v{version}-{memory}-{rom}-{batch}.so'
            subprocess.run(['g++','-O2','-std=c++11','-shared','-fPIC',
                '-DLPX4_ENABLE_ASM=0','-DLPX4_ENABLE_SPEECH=1','-DLPX4_ENABLE_SPEECH_COMPACT=1',
                '-DLPX4_COMPACT_ONLY=1','-DLPX4_ENABLE_INPUT_CALLBACK=1',
                f'-DLPX4_COMPACT_VERSION={5 if version==8 else version}',f'-DLPX4_MEMORY_PROFILE={memory}',
                *(['-DLPX4_ENABLE_SPARSE80=1'] if version==8 else []),
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

    def test_sparse80_profiles_tails_sources_and_lossless_repacking(self):
        for n in (1,19,20,21,39,40,41,79,80,81,159,160,161,319,320,321,641):
            old,expanded=sparse_fixture(n);new,stats=repack(old)
            self.assertEqual(new[2],15)
            self.assertLessEqual(len(new),len(old)-9)
            self.assertLessEqual(stats['payload_bits'],stats['input_payload_bits'])
            restored,_=repack(new,8);again,_=repack(restored)
            self.assertEqual(again,new)
            for domain in (0,1):
                expected=self.decode((5,0,1,1),expanded,domain)
                self.assertEqual(self.decode((8,0,1,1),old,domain),expected)
                for key in self.libs:
                    if key[0]==9:
                        for mode in (0,1,2,3,5):
                            self.assertEqual(self.decode(key,new,domain,mode),expected,(key,n,domain,mode))
        for style in ('static','clusters','changing'):
          for pre,bright in ((0,0),(1,1),(8192,64),(16383,11468),(16384,11469)):
            old,expanded=sparse_fixture(10240,style,pre,bright);new,_=repack(old)
            for domain in (0,1):
                expected=self.decode((5,0,1,1),expanded,domain)
                self.assertEqual(self.decode((8,0,1,1),old,domain),expected)
                self.assertEqual(self.decode((9,1,1,1),new,domain),expected)
        old,expanded=sparse_fixture(64000,'static');new,_=repack(old)
        self.assertEqual(self.decode((9,1,1,1),new),self.decode((5,0,1,1),expanded))
        # One loaded binary accepts alternating profiles without recompilation.
        for profile in (4,6,15,4,15,6):
            old,expected=(sparse_fixture(641) if profile==15 else (fixture(profile,641,145),None))
            new,_=repack(old)
            self.assertEqual(self.decode((9,1,1,1),new),self.decode((5,0,1,1),expected or old))

    def test_public_two_kbit_fixture_against_frozen_pcm_and_pwm(self):
        folder=ROOT/'tests/fixtures';meta=json.loads((folder/'chego-2k-v8.json').read_text())
        old=(folder/'chego-2k-v8.lpx').read_bytes();new,_=repack(old)
        self.assertEqual(hashlib.sha256(old).hexdigest(),meta['v8_sha256'])
        self.assertEqual(hashlib.sha256(new).hexdigest(),meta['v9_sha256'])
        self.assertLessEqual(len(old),meta['samples']*2//64)
        for domain,field in ((0,'s16_sha256'),(1,'pwm_sha256')):
            expected=self.decode((8,0,1,1),old,domain)
            self.assertEqual(hashlib.sha256(expected[2]).hexdigest(),meta[field])
            for key in self.libs:
                if key[0]==9:self.assertEqual(self.decode(key,new,domain),expected,key)

    def test_sparse80_strict_profiles_lengths_and_padding(self):
        old,_=sparse_fixture(321);good,stats=repack(old)
        bad=[good[:i] for i in range(len(good))]+[good+b'\0']
        for profile in (0,7,8,12,14,64,68,70,143,255):
            item=bytearray(good);item[2]=profile;bad.append(bytes(item))
        item=bytearray(good+b'\0');struct.pack_into('<H',item,11,len(item)-13);bad.append(bytes(item))
        if stats['payload_bits']%8:
            item=bytearray(good);item[-1]|=128;bad.append(bytes(item))
        for blob in bad:
            with self.assertRaises(ValueError):repack(blob)
            for key in self.libs:
                if key[0]==9:self.assertNotEqual(self.decode(key,blob)[1][1],0,key)
        with self.assertRaises(ValueError):repack(good,5)
        with self.assertRaises(ValueError):repack(fixture(4,320,145),8)

    def test_strict_new_payload_and_metadata_rejections(self):
        good,_=repack(fixture(6,321,18,'changing',True))
        bad=[good[:i] for i in range(len(good))]+[good+b'\0']
        for at,width,value in ((1,1,56),(2,1,14),(3,2,16000),(5,2,0),(5,2,64001),(7,2,16385),(9,2,11470)):
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
