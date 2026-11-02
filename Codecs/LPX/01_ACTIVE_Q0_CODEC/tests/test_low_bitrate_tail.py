"""Only played samples may influence a stored final packet's fitted fields."""
import unittest

import numpy as np

from encode_low_bitrate_speech import trial_group, search_excitation
import speech_compact as compact
import speech_sparse80 as sparse
from q0_model import coefficient_trace, table
from wav_lpc import pack_frames


class PlayedTailContracts(unittest.TestCase):
    def test_partial_group_loss_and_state_equal_exact_played_prefix(self):
        target=np.arange(320,dtype=np.int64)*17-1500
        co=np.zeros((320,10),np.int64)
        history,ring=np.zeros(10,np.int64),np.zeros(256,np.int64)
        for guard in (False,True):
            actual=trial_group(target,co,history,0,0,ring,0,80,100,23,10,23,7,8192,guard,73)
            expected=trial_group(target[:73],co[:73],history,0,0,ring,0,73,100,23,10,23,7,8192,guard)
            self.assertEqual(actual[0],expected[0])
            for left,right in zip(actual[1:5],expected[1:5]):
                np.testing.assert_array_equal(left,right)
            np.testing.assert_array_equal(actual[5][:73],expected[5])
            np.testing.assert_array_equal(actual[5][73:],0)

    def test_wholly_unplayed_group_preserves_all_incoming_state(self):
        target=np.full(320,30000,np.int64)
        co=np.full((320,10),999,np.int64)
        history=np.arange(10,dtype=np.int64)*7
        ring=np.arange(256,dtype=np.int64)%64-32
        result=trial_group(target,co,history,1234,-26,ring,80,80,100,23,10,0,-8,8192,True,73)
        self.assertEqual(result[0],0)
        np.testing.assert_array_equal(result[1],history)
        self.assertEqual(result[2:4],(1234,-26))
        np.testing.assert_array_equal(result[4],ring)
        np.testing.assert_array_equal(result[5],0)

    def test_fitting_ignores_padding_values_and_matches_full_container_model(self):
        n,stored=641,960
        prefix=np.asarray([(i*73)%4001-2000 for i in range(n)],np.int64)
        for sparse80 in (False,True):
            group,block=(80,320) if sparse80 else (20,160)
            shift=4 if sparse80 else 5
            vector=[3+5*i for i in range(10)] if sparse80 else [1+3*i for i in range(10)]
            spectra=[vector]*3
            vectors=[[(value<<shift)+(1<<(shift-1)) for value in row]
                     for row in spectra for _ in range(2)]
            co=coefficient_trace(pack_frames(vectors),stored)
            lags=np.full(stored//block,37,np.int64)
            results=[]
            for pad in (-28000,30000):
                target=np.r_[prefix,np.full(stored-n,pad,np.int64)]
                results.append(search_excitation(target,co,table('scale_table.inc'),lags,
                                                 8192,sparse80,True,True,n))
            for left,right in zip(*results):
                np.testing.assert_array_equal(left,right)
            params,pulses,pcm,_=results[0]
            np.testing.assert_array_equal(pcm[n:],0)
            blob=(sparse.pack(n,spectra,params.tolist(),pulses.tolist(),8192) if sparse80 else
                  compact.pack(n,4,spectra,params.tolist(),pulses.tolist(),8192)[0])
            modeled=(sparse.decode_model if sparse80 else compact.decode_model)(blob)
            np.testing.assert_array_equal(pcm[:n],modeled)


if __name__=='__main__':
    unittest.main()
