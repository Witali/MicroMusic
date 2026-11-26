"""Separate prospective gate for automatic P3 fine-grid integration."""
import hashlib,json,os,re,subprocess,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[5]
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT=REPO/'build/compact-quality/round2-integration-independent'
EXPECTED={
 'host/LpxAccuracy.cpp':'a7206f9e34c62f35fbf89c54d135bbd59b699abb9de2670271686bd909d7d91c',
 'host/LpxAccuracy.h':'1d20e25688aa42c74afeff70bf9d2798e312ec33143882e0827e62c7a7b8abfa',
 'host/LpxAdaptiveController.h':'ffcdc8533e31bc4c19fbdfbaa0d041b823294ddfbc6c741af9ffec30a30ee38d',
}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def native(path):
 p=Path(path).resolve()
 return '/mnt/'+p.drive[0].lower()+'/'+('/'.join(p.parts[1:])) if os.name=='nt' and os.environ.get('LPX_TEST_WSL') else str(p)
class IntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  OUTPUT.mkdir(parents=True,exist_ok=True)
  for name,expected in EXPECTED.items():
   if digest(ACTIVE/name)!=expected:raise AssertionError('Unexpected integration freeze: '+name)
  cls.prefix=['wsl','-d',os.environ['LPX_TEST_WSL'],'--'] if os.name=='nt' and os.environ.get('LPX_TEST_WSL') else []
  cfg=(REPO/'web-player/scripts/lib/lpx-build.mjs').read_text(encoding='utf-8')
  names=re.findall(r"'([^']+\.cpp)'",cfg.split('export const hostSources=host([')[1].split(']);')[0])
  defines=re.findall(r"'([^']+)'",cfg.split('export const portableDefines=[')[1].split('];')[0])
  sources=[ACTIVE/'src/Lpx4HybridCore.cpp',ACTIVE/'host/LpxEncoder.cpp',*(ACTIVE/'host'/n for n in names),ACTIVE/'host/LpxAdaptiveApi.cpp',HERE/'integration.cpp']
  inputs=[*sources,*(ACTIVE/'host').glob('*.h'),*(ACTIVE/'src').glob('*.h'),*(ACTIVE/'host').glob('*.inc'),*(ACTIVE/'src').glob('*.inc')]
  before={p.relative_to(REPO).as_posix():digest(p) for p in inputs}
  cls.receipt=dict(schema='lpx-p3-round2-integration-independent-v1',implementation_sha256=EXPECTED,passed=False,
      compiler=subprocess.check_output(cls.prefix+['g++','--version'],text=True).splitlines()[0],sources=before,builds={},results={})
  for enabled in (1,0):
   command=['g++','-O2','-std=c++11','-ffp-contract=off',*('-D'+d for d in defines),f'-DLPX_ENCODER_COMPACT_ENSEMBLE={enabled}',
       '-include',native(ACTIVE/'host/LpxHostWorkspace.h'),'-I'+native(ACTIVE/'host'),'-I'+native(ACTIVE/'src'),*(native(p) for p in sources),'-o',native(OUTPUT/f'integration-{enabled}')]
   built=subprocess.run(cls.prefix+command,capture_output=True,text=True)
   if built.returncode:raise AssertionError(built.stdout+built.stderr)
   if before!={p.relative_to(REPO).as_posix():digest(p) for p in inputs}:raise RuntimeError('Inputs changed during gate build')
   cls.receipt['builds'][str(enabled)]=dict(command=command,binary_sha256=digest(OUTPUT/f'integration-{enabled}'))
 @classmethod
 def tearDownClass(cls):
  cls.receipt['passed']=len(cls.receipt['results'])==4 and all(v['passed'] for v in cls.receipt['results'].values())
  (OUTPUT/'receipt.json').write_text(json.dumps(cls.receipt,indent=2)+'\n',encoding='utf-8')
 def check(self,mode,both=False):
  outputs={};passed=True
  for enabled in ((1,0) if both else (1,)):
   started=time.monotonic();done=subprocess.run(self.prefix+[native(OUTPUT/f'integration-{enabled}'),mode],capture_output=True,text=True)
   outputs[str(enabled)]=dict(returncode=done.returncode,stdout=done.stdout.strip(),stderr=done.stderr.strip(),wall_seconds=time.monotonic()-started)
   passed&=done.returncode==0 and 'PASS' in done.stdout
  if both and mode=='automatic':
   excluded=[[line for line in output['stdout'].splitlines() if line.startswith('EXCLUDED ')] for output in outputs.values()]
   passed&=len(excluded[0])==20 and excluded[0]==excluded[1]
  self.receipt['results'][mode]=dict(passed=bool(passed),outputs=outputs)
  self.assertTrue(passed,json.dumps(outputs,indent=2))
 def test_partial_tail_relabel_and_odd_rank_native_identity(self):self.check('identity')
 def test_complete_eligibility_switches_and_boundaries(self):self.check('eligibility',True)
 def test_exact_optional_rollback_and_unchanged_selector(self):self.check('selection',True)
 def test_actual_automatic_scoping_switch_zero_and_c_abi_pack(self):self.check('automatic',True)
if __name__=='__main__':unittest.main(verbosity=2)
