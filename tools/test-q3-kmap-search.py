"""Map-fit proposals, complete exports and explicit PC-only qualification."""
import importlib.util
import json
from pathlib import Path
import random
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('q3_kmap_test_search',ROOT/'tools/probe-q3-kmap.py')
fit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fit
spec.loader.exec_module(fit)


class KmapSearchTests(unittest.TestCase):
    def test_proposals_keep_maps_stable_and_frames_do_not_share_storage(self):
        f = np.array([[40,3,0x78,0x88,0x88,0x88]]*12,np.uint8)
        d = np.full(12,256,np.uint16)
        state = fit.search.State(f,d,fit.codec.legacy_tables(),False,1)
        fingerprint = (f.tobytes(),d.tobytes(),state.book.tobytes())
        rng = random.Random(23501)
        changed_maps = False
        for _ in range(256):
            trial = fit.mutate(state,rng)
            fit.codec.validate_tables(trial.book)
            changed_maps |= not np.array_equal(trial.book[4:],state.book[4:])
        self.assertTrue(changed_maps)
        self.assertEqual(fingerprint,(f.tobytes(),d.tobytes(),state.book.tobytes()))

    def test_zero_proposal_run_exports_real64_byte_layout_and_explicit_pc_flags(self):
        build = ROOT/'build';build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='test-kmap-',dir=build) as name:
            folder = Path(name)
            reference = folder/'reference.wav'
            sf.write(reference,.2*np.sin(np.arange(6144)*2*np.pi/40),7500,subtype='FLOAT')
            model = folder/'model.json'
            model.write_text(json.dumps(dict(schema='hq4-q3-pulsebook-v1',tilt_shift=1,nearest=False,
                frames=[[40,3,0x88,0x88,0x88,0x88]]*24,durations=[256]*24)))
            result = fit.run(reference,[model],folder/'out',proposals=0)
            self.assertFalse(result['avr_qualified'])
            self.assertEqual(result['samples'],6144)
            self.assertEqual(len(result['initial']),25)
            for endpoint in ('balanced','best_stoi','best_spectrum'):
                output = folder/'out'/endpoint
                saved = json.loads((output/'model.json').read_text())
                tables = np.array(saved['pulsebook']+saved['coefficient_maps'],np.int8)
                self.assertEqual((output/'eeprom.bin').read_bytes(),fit.codec.pack_eeprom(tables))
                self.assertEqual(len((output/'expected.raw').read_bytes()),6144)
                quality = json.loads((output/'quality.json').read_text())
                self.assertFalse(quality['avr_verified'])
                self.assertFalse(quality['avr_assembled'])
                self.assertEqual(quality['eeprom_bytes'],64)

    def test_negative_proposal_count_is_rejected_before_search(self):
        build = ROOT/'build';build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='test-kmap-invalid-',dir=build) as name:
            reference = Path(name)/'reference.wav'
            sf.write(reference,np.ones(3072)*.1,7500,subtype='FLOAT')
            with self.assertRaisesRegex(ValueError,'nonnegative'):
                fit.run(reference,[],Path(name)/'out',proposals=-1)


if __name__ == '__main__': unittest.main()
