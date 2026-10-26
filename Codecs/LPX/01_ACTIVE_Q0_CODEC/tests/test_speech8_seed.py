import unittest
import numpy as np
from batch_decoder import BatchSession
from test_speech_v4 import fixture
from speech_v4 import decode_model
from refine_speech8 import legacy_seed
from speech_compact import repack,decode_model as compact_model


class Speech8SeedTests(unittest.TestCase):
    def test_speech_excitation_and_spectrum_survive_legacy_transcode(self):
        with BatchSession('batch',v3_features=24) as decoder:
            for profile in (4,6):
                for count in (1,19,159,160,319,320,321,641):
                    speech=fixture(profile,count);legacy=legacy_seed(speech)
                    self.assertIn(legacy[4],(2,3))
                    np.testing.assert_array_equal(decoder.decode_one_s16(legacy,count),decode_model(speech))

    def test_compact_extras_survive_legacy_transcode_without_speech_decoder(self):
        with BatchSession('batch',v3_features=24) as decoder, BatchSession('batch',speech=True,speech_compact=True) as speech_decoder:
            for profile in (4,6):
                for count in (1,19,159,160,319,320,321,641):
                    original=fixture(profile,count);chunks=((count+319)//320)*8
                    extras=[((0,20,39)[i%3],-8 if i&1 else 7) for i in range(chunks)]
                    for innovations in (None,extras):
                        speech=repack(original,extras=innovations)[0];legacy=legacy_seed(speech)
                        self.assertIn(legacy[4],(2,3));self.assertEqual(legacy[8:16],speech[8:16])
                        pcm=decoder.decode_one_s16(legacy,count)
                        np.testing.assert_array_equal(pcm,compact_model(speech))
                        np.testing.assert_array_equal(pcm,speech_decoder.decode_one_s16(speech,count))


if __name__=='__main__':unittest.main()
