"""The common -30 dB policy follows input gain and never gates PCM."""
from pathlib import Path
import sys,unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from level_policy import DEFAULT_LEVEL_FLOOR_DB,relative_energy_floor,preserves_activity


class LevelPolicyTests(unittest.TestCase):
    def test_minus_30_db_is_relative_power_for_every_input_level(self):
        x=np.resize(np.array([-16000,-8000,0,8000,16000],np.int64),640)
        self.assertEqual(DEFAULT_LEVEL_FLOOR_DB,-30.)
        original=x.copy();base=relative_energy_floor(x)
        self.assertAlmostEqual(base,float(np.mean(x.astype(float)**2))*.001)
        for divisor in (2,4,16):
            quiet=x//divisor
            self.assertAlmostEqual(relative_energy_floor(quiet),base/(divisor*divisor))
        np.testing.assert_array_equal(x,original)

    def test_silence_and_integer_precision_have_a_numerical_floor(self):
        for x in (np.zeros(80,np.int16),np.array([-1,0,1],np.int16)):
            self.assertEqual(relative_energy_floor(x),1.)
        self.assertEqual(relative_energy_floor(np.array([-1000,1000],np.int16),-20.),10000.)

    def test_invalid_threshold_or_signal_is_rejected(self):
        for db in (float('nan'),float('inf'),1.):
            with self.assertRaises(ValueError):relative_energy_floor(np.ones(80,np.int16),db)
        for x in (np.array([],np.int16),np.array([float('nan')]),np.array([float('inf')])):
            with self.assertRaises(ValueError):relative_energy_floor(x)

    def test_quiet_nonzero_signal_is_not_silenced_by_an_absolute_floor(self):
        from rate_distortion import quantize_rate
        from q0_model import table
        co=np.zeros((80,10),np.int64);steps=table('scale_table.inc')
        for amplitude in (1000,250,62):
            ref=np.full(80,amplitude,np.int64)
            q,_,widths,_,_=quantize_rate(ref,co,steps,0,0,.2,True)
            self.assertGreater(widths[0],0)
            self.assertTrue(np.any(q))
        q,_,widths,_,_=quantize_rate(np.zeros(80,np.int64),co,steps,0,0,.2,True)
        self.assertEqual(widths[0],0)
        self.assertFalse(np.any(q))

    def test_activity_guard_uses_relative_level_without_modifying_pcm(self):
        x=np.resize(np.array([-4000,4000],np.int16),800);y=x.copy()
        self.assertTrue(preserves_activity(x,y))
        y[240:480]=0;before=y.copy()
        self.assertFalse(preserves_activity(x,y))
        self.assertFalse(preserves_activity(x//16,y//16))
        np.testing.assert_array_equal(y,before)
        self.assertTrue(preserves_activity(np.zeros(800,np.int16),np.zeros(800,np.int16)))


if __name__=='__main__':unittest.main()
