import unittest
import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
from speech_v4 import decode_model
from refine_speech8 import legacy_seed


class Speech8SeedTests(unittest.TestCase):
    def test_speech_excitation_and_spectrum_survive_legacy_transcode(self):
        with BatchSession('batch',v3_features=24) as decoder:
            for profile in (4,6):
                for count in (1,19,159,160,319,320,321,641):
                    speech=fixture(profile,count);legacy=legacy_seed(speech)
                    self.assertIn(legacy[4],(2,3))
                    np.testing.assert_array_equal(decoder.decode_one_s16(legacy,count),decode_model(speech))


if __name__=='__main__':unittest.main()
