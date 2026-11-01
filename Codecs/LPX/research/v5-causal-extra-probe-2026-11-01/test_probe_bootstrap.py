import os
from pathlib import Path
import subprocess
import sys
import unittest

from probe import Inputs,bind_production,bridge_native,HERE


class Bootstrap(unittest.TestCase):
    def test_standalone_recipe_import_does_not_load_codecs(self):
        script='import sys;sys.path.insert(0,sys.argv[1]);import probe;assert "speech_compact" not in sys.modules'
        result=subprocess.run([sys.executable,'-c',script,str(HERE)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,'Clean synthetic probe import failed')

    @unittest.skipUnless(os.environ.get('CAUSAL_NATIVE_CASES'),'Closed native metadata is opt-in')
    def test_exact_native_metadata_and_source_bridge_only(self):
        inputs=Inputs();root=HERE.parents[3]
        bind_production(root,'654ada49')
        native,bridge=bridge_native(root,Path(os.environ['CAUSAL_NATIVE_CASES']),inputs)
        self.assertEqual(set(native),{'common','v5-only'});self.assertEqual(bridge['new_native_builds'],0)
        self.assertTrue(all(Path(name).suffix.lower() not in ('.wav','.l4hy','.l4h','.pcm') for name in inputs.pins))
        inputs.verify()


if __name__=='__main__':unittest.main()
