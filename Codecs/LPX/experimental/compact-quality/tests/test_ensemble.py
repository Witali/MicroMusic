"""Independent synthetic gate for the separate existing-encoder ensemble arm."""
import hashlib,json,os,re,subprocess,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
BENCHMARK=HERE.parent/'benchmark_ensemble.cpp'
EXPECTED='93ad5a02dacdb91f643dde70b26270df3d73d405d3bc88a9dfa86424ce426a81'
OUTPUT=REPO/'build/compact-quality/p3-ensemble-independent'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def native(path):
 p=Path(path).resolve()
 return '/mnt/'+p.drive[0].lower()+'/'+('/'.join(p.parts[1:])) if os.name=='nt' and os.environ.get('LPX_TEST_WSL') else str(p)
class EnsembleTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  OUTPUT.mkdir(parents=True,exist_ok=True)
  if digest(BENCHMARK)!=EXPECTED:raise AssertionError('Unexpected frozen ensemble adapter')
  cls.prefix=['wsl','-d',os.environ['LPX_TEST_WSL'],'--'] if os.name=='nt' and os.environ.get('LPX_TEST_WSL') else []
  cfg=(REPO/'web-player/scripts/lib/lpx-build.mjs').read_text(encoding='utf-8')
  names=re.findall(r"'([^']+\.cpp)'",cfg.split('export const hostSources=host([')[1].split(']);')[0])
  defines=re.findall(r"'([^']+)'",cfg.split('export const portableDefines=[')[1].split('];')[0])
  sources=[ACTIVE/'src/Lpx4HybridCore.cpp',ACTIVE/'host/LpxEncoder.cpp',*(ACTIVE/'host'/n for n in names),HERE/'ensemble.cpp']
  inputs=[*sources,BENCHMARK,REPO/'Codecs/LPX/research/lbg1-2026-11-26/probe.cpp',*(ACTIVE/'host').glob('*.h'),*(ACTIVE/'src').glob('*.h'),*(ACTIVE/'host').glob('*.inc'),*(ACTIVE/'src').glob('*.inc')]
  before={p.relative_to(REPO).as_posix():digest(p) for p in inputs}
  command=['g++','-O2','-std=c++11','-ffp-contract=off',*('-D'+d for d in defines),'-include',native(ACTIVE/'host/LpxHostWorkspace.h'),'-I'+native(ACTIVE/'host'),'-I'+native(ACTIVE/'src'),*(native(p) for p in sources),'-o',native(OUTPUT/'ensemble-tests')]
  built=subprocess.run(cls.prefix+command,capture_output=True,text=True)
  if built.returncode:raise AssertionError(built.stdout+built.stderr)
  if before!={p.relative_to(REPO).as_posix():digest(p) for p in inputs}:raise RuntimeError('Inputs changed during gate build')
  cls.receipt=dict(schema='lpx-p3-ensemble-independent-v1',benchmark_sha256=EXPECTED,passed=False,
      compiler=subprocess.check_output(cls.prefix+['g++','--version'],text=True).splitlines()[0],command=command,sources=before,
      binary_sha256=digest(OUTPUT/'ensemble-tests'),results={})
 @classmethod
 def tearDownClass(cls):
  cls.receipt['passed']=len(cls.receipt['results'])==4 and all(v['returncode']==0 for v in cls.receipt['results'].values())
  (OUTPUT/'receipt.json').write_text(json.dumps(cls.receipt,indent=2)+'\n',encoding='utf-8')
 def check(self,mode):
  done=subprocess.run(self.prefix+[native(OUTPUT/'ensemble-tests'),mode],capture_output=True,text=True)
  self.receipt['results'][mode]=dict(returncode=done.returncode,stdout=done.stdout.strip(),stderr=done.stderr.strip())
  self.assertEqual(done.returncode,0,done.stdout+done.stderr);self.assertIn('PASS',done.stdout)
 def test_policy_relabel_leaves_all_physical_data_identical(self):self.check('identity')
 def test_odd_grid_uses_fine_checker_and_detects_wrong_forced_p3(self):self.check('grid')
 def test_strict_original_B0_protection_and_invalid_geometry(self):self.check('protection')
 def test_search_errors_fallback_and_valid_raw_not_replaced(self):self.check('fallback')
if __name__=='__main__':unittest.main(verbosity=2)
