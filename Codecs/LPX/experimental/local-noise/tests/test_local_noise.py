"""Independent local-noise experiment contracts; no production edits.

Run in Linux/WSL with g++; standard Python library only. The exact production
host composition is reused, plus the experimental scorer and this test driver.
Generated native binaries, source fingerprints and logs stay in ignored build/.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT=REPO/'build/local-noise-independent-tests'


class LocalNoiseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True,exist_ok=True)
        config=(REPO/'web-player/scripts/lib/lpx-build.mjs').read_text()
        names=re.findall(r"'([^']+\.cpp)'",config.split('export const hostSources=host([')[1].split(']);')[0])
        defines=re.findall(r"'([^']+)'",config.split('export const portableDefines=[')[1].split('];')[0])
        sources=[ACTIVE/'src/Lpx4HybridCore.cpp',ACTIVE/'host/LpxEncoder.cpp',
                 *(ACTIVE/'host'/name for name in names),HERE.parent/'LocalNoise.cpp',HERE/'local_noise.cpp']
        inputs=[*sources,*(ACTIVE/'host').glob('*.h'),*(ACTIVE/'src').glob('*.h'),HERE.parent/'LocalNoise.h']
        before={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        command=['g++','-O2','-std=c++11','-ffp-contract=off',*('-D'+define for define in defines),
                 '-include',str(ACTIVE/'host/LpxHostWorkspace.h'),
                 '-I'+str(ACTIVE/'src'),'-I'+str(ACTIVE/'host'),'-I'+str(HERE.parent),
                 *(str(p) for p in sources),'-o',str(OUTPUT/'local-noise-tests')]
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
        if before!={p.relative_to(REPO).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}:
            raise RuntimeError('Inputs changed during the independent build')
        cls.receipt=dict(compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0],
                         command=command,sources=before,results={})

    @classmethod
    def tearDownClass(cls):
        (OUTPUT/'receipt.json').write_text(json.dumps(cls.receipt,indent=2)+'\n',encoding='utf-8')

    def check(self,mode):
        result=subprocess.run([str(OUTPUT/'local-noise-tests'),mode],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS',result.stdout)
        self.receipt['results'][mode]=result.stdout.strip()

    def test_independent_spectral_oracle_and_mask_immutability(self):self.check('metric')
    def test_quiet_unvoiced_transient_and_target_contracts(self):self.check('fallback')
    def test_bounded_fixed_byte_stream_search_and_native_decode(self):self.check('search')
    def test_admission_floors_and_continuation(self):self.check('admission')


if __name__=='__main__':unittest.main(verbosity=2)
