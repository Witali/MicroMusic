from pathlib import Path
import struct
import sys
import unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from batch_decoder import BatchSession
from compact_format import pack, put_lsf_rice, get_lsf_rice
from lpx4 import encode, decode, BitWriter, BitReader, put_chunk, HUFF3
from rice_v4_reference import write_scale
from wav_lpc import pack_frames
from lossless_repack import optimize_excitation, optimize_scales


def source():
    rng=np.random.default_rng(65032);n=1287
    vectors=[[round(1023*i/11)+d for i in range(1,11)] for d in (0,1,-1,4,4,0,40,39,39)]
    frames=pack_frames(vectors)
    blocks=[]
    for index in range((n+79)//80):
        count=min(80,n-index*80)
        if index in (2,3,11):b=0;q=[0]*count
        else:
            b=(3,3,3,2,2,4)[index%6];q=rng.integers(-(1<<(b-1)),1<<(b-1),count).tolist()
            if index%3==0:q=[0]*count;q[min(5,count-1)]=1
        blocks.append({'bits':b,'scale':(0,0,91,91,130)[index%5],'q':q})
    raw=struct.pack('<4sBBHIHHHH',b'L3AV',1,3,8000,n,13926,1000,160,80)
    return optimize_excitation(encode({'raw':raw,'frames':frames,'blocks':blocks},fast=True)[0])[0]


class CompactFormatTests(unittest.TestCase):
    def test_all_feature_combinations_match_native_pcm_pwm_and_lsf(self):
        blob=source();frames,blocks,q=decode(blob)
        with BatchSession('batch',v3_features=124) as dec:
            pcm=dec.decode_one_s16(blob,len(q));pwm=dec.decode_one(blob,len(q))
            self.assertIsNotNone(pcm)
            for features in range(0,125,4):
                packed,_=pack(blob,features)
                newframes,newblocks,newq=decode(packed)
                self.assertEqual(frames,newframes);self.assertEqual(q,newq)
                np.testing.assert_array_equal(dec.decode_one_s16(packed,len(q)),pcm)
                np.testing.assert_array_equal(dec.decode_one(packed,len(q)),pwm)

    def test_explicit_compile_features_and_truncation(self):
        blob=source();packed,_=pack(blob,32);n=int.from_bytes(blob[8:12],'little')
        with self.assertRaisesRegex(ValueError,'requires L4HY v2'):optimize_scales(packed)
        with self.assertRaisesRegex(ValueError,'requires L4HY v2'):optimize_excitation(packed)
        with BatchSession('batch') as dec:self.assertIsNone(dec.decode_one(packed,n))
        with BatchSession('batch',v3_features=32) as dec:
            self.assertIsNotNone(dec.decode_one(packed,n))
            unsupported=bytearray(packed);unsupported[5]|=64
            self.assertIsNone(dec.decode_one(bytes(unsupported),n))
            for length in range(len(packed)):
                self.assertIsNone(dec.decode_one(packed[:length],n))

    def test_lsf_signed_byte_rice_escape_is_bounded_and_exact(self):
        for k in (0,2):
            for delta in range(-128,128):
                w=BitWriter();put_lsf_rice(w,delta&255,k);self.assertLessEqual(w.total,16)
                w.aligned();self.assertEqual(get_lsf_rice(BitReader(w.get()),k),delta&255)

    def test_repeated_huffman_still_validates_new_block_width(self):
        header=struct.pack('<4sBBHIHHHH',b'L4HY',3,27,8000,81,0,0,160,80)
        w=BitWriter();w.put(1,1);w.put(0,1)
        for v in [round(1023*i/11) for i in range(1,11)]:w.put(v&255,8);w.put(v>>8,2)
        w.put(1,1);w.put(3,3);write_scale(w,0,0)
        w.put(1,1);put_chunk(w,[0]*40,[],3,('direct',7))
        w.put(0,1)
        for _ in range(40):
            for bit in HUFF3[0]:w.put(int(bit),1)
        w.put(1,1);w.put(2,3);write_scale(w,0,0)
        w.put(0,1)  # Reusing k7 is invalid after changing width to 2.
        w.aligned()
        with BatchSession('batch',v3_features=24) as dec:
            self.assertIsNone(dec.decode_one(header+w.get(),81))


if __name__=='__main__':unittest.main()
