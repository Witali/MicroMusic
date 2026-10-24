"""Eight forms must preserve legacy gains/bytes and have strict new headers."""
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ATtiny13A/Sound/codec'))
import q3_pulsebook as old
import q3_pulsebook8 as new
from hq4_core import pack_stream as old_pack


class Pulsebook8Tests(unittest.TestCase):
    def frames(self):
        f=np.array([[p,(i%4)*16+(i%16),0x79,0x97,0x88,0x79]
                    for i,p in enumerate([0,1,2,4,16,40,63,64,90,126]*2)],np.uint8)
        return f,np.array(([64,128,192,256]*5),np.uint16)

    def test_first_four_forms_preserve_old_stream_and_all_pcm(self):
        f,d=self.frames();book=old.legacy_tables();eight=np.vstack((book,book))
        self.assertEqual(new.pack_stream(f,d),old_pack(f,d))
        for nearest in (False,True):
            for tilt in (0,1,2):
                a,c=old.render(f,d,book,tilt,nearest);b,e=new.render(f,d,eight,tilt,nearest)
                np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(c,e)

    def test_all_selectors_and_gain_levels_roundtrip_without_aliasing(self):
        f=np.array([[40,m*16+g,0x79,0x97,0x88,0x79] for m in range(8) for g in range(16)],np.uint8)
        d=np.full(len(f),64,np.uint16)
        got,durations=new.unpack_stream(new.pack_stream(f,d))
        np.testing.assert_array_equal(got,f);np.testing.assert_array_equal(durations,d)
        old_length=len(old_pack(f[:64],d[:64]))
        self.assertEqual(len(new.pack_stream(f,d)),old_length+64*3)

    def test_extended_headers_store_the_extra_selector_bit_without_extra_bytes(self):
        f,d=self.frames();f[:,0]=90
        before=new.pack_stream(f,d)
        f[:,1] |= 64
        after=new.pack_stream(f,d)
        self.assertEqual(len(before),len(after))
        np.testing.assert_array_equal(new.unpack_stream(after)[0],f)
        for payload in (after[:1],b'\xff',b'\xc8\x28\x00\x88\x88\x88\x88',b'\x28\x40'):
            with self.assertRaises(ValueError):new.unpack_stream(payload)

    def test_physical_tables_and_prefixes_do_not_overlap(self):
        for width,packing in ((4,'raw'),(4,'nibble'),(8,'raw'),(8,'nibble'),(16,'nibble')):
            book=np.zeros((8,16),np.int8)
            book[:,:width]=((np.arange(8*width).reshape(8,width)%15)-7)
            encoded=new.encode_book(book,width,packing)
            np.testing.assert_array_equal(new.decode_book(encoded,width,packing),book)
            layout=new.storage(book,b'a'*620,width,packing)
            self.assertEqual(len(layout['eeprom']),64)
            self.assertEqual(layout['eeprom'][layout['prefix_start']:layout['prefix_end']]+layout['flash_suffix'],b'a'*620)
        with self.assertRaises(ValueError):new.encode_book(np.zeros((8,16),np.int8),16,'raw')
        book=np.zeros((8,16),np.int8);book[7,4]=1
        with self.assertRaisesRegex(ValueError,'nonzero'):new.encode_book(book,4,'nibble')

    def test_frames_and_sizes_are_validated_before_encoding(self):
        f,d=self.frames();book=np.zeros((8,16),np.int8)
        for column,value in ((0,127),(1,128),(2,0x80)):
            bad=f.copy();bad[0,column]=value
            with self.assertRaises(ValueError):new.validate(bad,d,book)
        with self.assertRaises(ValueError):new.validate(f,d,book,samples=1)
        with self.assertRaises(ValueError):new.validate(f,d,book,stream_budget=1)

    def test_duplicate_and_inactive_selectors_recode_without_changing_pcm(self):
        f,d=self.frames();f[:,1]|=64
        book=np.vstack((old.legacy_tables(),old.legacy_tables()))
        recoded=new.canonicalize_selectors(f,book)
        self.assertTrue(np.all(recoded[:,1]<64))
        self.assertLess(len(new.pack_stream(recoded,d)),len(new.pack_stream(f,d)))
        for nearest in (False,True):
            before,counts=new.render(f,d,book,1,nearest)
            after,other=new.render(recoded,d,book,1,nearest)
            np.testing.assert_array_equal(before,after);np.testing.assert_array_equal(counts,other)


if __name__=='__main__':unittest.main()
