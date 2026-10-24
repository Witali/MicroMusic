"""Lossless active-form compaction and complete-image cost contracts."""
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_adaptive as adaptive
import q3_pulsebook8 as codec


class AdaptiveTests(unittest.TestCase):
    def fixture(self,count):
        b=np.zeros((8,16),np.int8);b[:,0]=np.arange(8)-7
        modes=np.arange(32)%max(1,count)
        f=np.array([[40,int(m)*16+(1 if count else 0),0x88,0x88,0x88,0x88] for m in modes],np.uint8)
        d=np.tile(np.array([64,128,192,256],np.uint16),8)
        return f,d,b

    def test_every_active_count_preserves_pcm_counters_and_reachable_eeprom(self):
        for count in range(9):
            f,d,b=self.fixture(count);old,c=codec.render(f,d,b)
            for layout in adaptive.layouts(f,d,b):
                pcm,counts=codec.render(layout['frames'],d,layout['book'])
                np.testing.assert_array_equal(pcm,old);np.testing.assert_array_equal(counts,c)
                self.assertEqual(layout['active_forms'],count)
                self.assertEqual(layout['decoder_forms'],4 if count<=4 else 8)
                self.assertEqual(len(layout['eeprom']),64)
                start,end=layout['prefix_start'],layout['prefix_end']
                self.assertEqual(layout['eeprom'][start:end]+layout['flash_suffix'],layout['payload'])
                stride=layout['width'] if layout['packing']=='raw' else layout['width']//2
                physical=layout['eeprom'][:start].ljust(8*stride,b'\0')
                half=4*stride
                decoded=np.vstack((codec.decode_four(physical[:half],layout['width'],layout['packing']),
                    codec.decode_four(physical[half:],layout['width'],layout['packing'])))
                np.testing.assert_array_equal(decoded,layout['book'])

    def test_expensive_header_frequency_determines_the_four_cheap_selectors(self):
        f,d,b=self.fixture(8)
        f[:,0]=90;d[:]=192
        f[-4:,0]=40;d[-4:]=64
        got,book,info=adaptive.compact(f,d,b)
        self.assertEqual(set(info['source_rows'][:4]),{4,5,6,7})
        self.assertLess(len(codec.pack_stream(got,d)),len(codec.pack_stream(f,d)))
        np.testing.assert_array_equal(codec.render(got,d,book)[0],codec.render(f,d,b)[0])

    def test_simple_sound_uses_one_row_and_a_smaller_real_decoder_budget(self):
        f,d,b=self.fixture(1);layout=adaptive.select(f,d,b)
        self.assertEqual((layout['stored_forms'],layout['packing'],layout['book_bytes']),(1,'raw',4))
        self.assertEqual((layout['code_bytes'],layout['prefix_bytes']),(398,60))
        self.assertEqual(layout['maximum_stream_bytes'],685)
        f,d,b=self.fixture(8);b[7]=b[1]
        got,_,info=adaptive.compact(f,d,b)
        self.assertEqual(info['active_forms'],7)
        self.assertLessEqual(int(got[:,1].max())>>4,6)


if __name__=='__main__':unittest.main()
