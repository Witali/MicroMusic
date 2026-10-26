"""A lower PCM error may cross a real PWM boundary and become worse."""
import unittest
import numpy as np
from benchmark_profile_development import point,choose

class ProfileSelectionTests(unittest.TestCase):
    def test_rejects_lower_pcm_error_with_worse_playback(self):
        ref=np.full(400,1136,np.int16)
        baseline=point(b'old',np.full(400,1134,np.int16),ref,'music','baseline')
        candidate=point(b'new',ref.copy(),ref,'music','candidate')
        self.assertLess(candidate[2]['full_sse'],baseline[2]['full_sse'])
        chosen,report=choose([candidate],baseline,ref,'music',100)
        self.assertEqual(chosen[0],b'old');self.assertEqual(report['rejected_by_pwm'],1)

    def test_perfect_rollback_and_byte_cap(self):
        ref=np.zeros(400,np.int16);base=point(b'base',ref.copy(),ref,'music','baseline')
        too_large=point(b'longer',ref.copy(),ref,'music','oversized')
        chosen,_=choose([too_large],base,ref,'music',4);self.assertEqual(chosen[0],b'base')
        with self.assertRaises(ValueError):choose([],base,ref,'music',3)

if __name__=='__main__':unittest.main()
