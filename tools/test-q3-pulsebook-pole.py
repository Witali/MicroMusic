"""Independent arithmetic coverage for the separately tagged -15/16 coefficient."""
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q3_pulsebook as old
import q3_pulsebook_pole as new


class PoleTests(unittest.TestCase):
    def test_every_signed_input_and_coefficient_matches_scalar_rule(self):
        for nearest in (False,True):
            for a in range(-128,128):
                for k in range(-8,8):
                    if k==-8:
                        expected=(-15*a+(8 if nearest else 0))//16
                    else:
                        adjusted=(((-a if k<0 else a)+128)&255)-128
                        expected=(adjusted*abs(k)+(4 if nearest else 0))//8
                        expected=((expected+128)&255)-128
                    self.assertEqual(new.multiply(a,k,nearest),expected,(a,k,nearest))

    def test_old_streams_and_all_modes_stay_byte_exact(self):
        f=np.array([[42,(mode<<4)|2,0x97,0x79,0x97,0x79] for mode in range(4)],np.uint8)
        d=np.array([128,192,64,256],np.uint16)
        for nearest in (False,True):
            before=old.render(f,d,old.legacy_tables(),1,nearest)
            after=new.render(f,d,new.legacy_tables(),1,nearest)
            np.testing.assert_array_equal(before[0],after[0])
            np.testing.assert_array_equal(before[1],after[1])

    def test_new_code_has_distinct_schema_and_descriptor_is_not_old_format(self):
        self.assertNotEqual(old.SCHEMA,new.SCHEMA)
        f=np.array([[40,1,0x80,0x88,0x88,0x88]],np.uint8)
        d=np.array([256],np.uint16)
        with self.assertRaises(ValueError): old.validate(f,d,old.legacy_tables())
        new.validate(f,d,new.legacy_tables())
        pcm,counts=new.render(f,d,new.legacy_tables(),1,True)
        self.assertEqual(len(pcm),256)
        self.assertFalse(np.any(counts))


if __name__=='__main__': unittest.main()
