"""Independent paired pre-extension/Long gate; no audiobook encoding."""
import hashlib,json,os,re,subprocess,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[5];ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT=REPO/'build/compact-quality/audiobook-study/independent';PRE=OUTPUT.parent/'pre-long'
EXPECTED={'current_cpp':'858489709bf077718ffb35a676ff7d4b99ab5a9905097ae54e154bea64fc7340',
 'current_h':'a50478c45d40539f276be84dd2fe80999b0cbebb1cdfdb55f2ae5c5dda27d2dc',
 'previous_cpp':'a7206f9e34c62f35fbf89c54d135bbd59b699abb9de2670271686bd909d7d91c',
 'previous_h':'1d20e25688aa42c74afeff70bf9d2798e312ec33143882e0827e62c7a7b8abfa'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def native(p):
 p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+'/'+('/'.join(p.parts[1:])) if os.name=='nt' and os.environ.get('LPX_TEST_WSL') else str(p)
class LongTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  OUTPUT.mkdir(parents=True,exist_ok=True);cls.prefix=['wsl','-d',os.environ['LPX_TEST_WSL'],'--'] if os.name=='nt' and os.environ.get('LPX_TEST_WSL') else []
  for name,path in [('current_cpp',ACTIVE/'host/LpxAccuracy.cpp'),('current_h',ACTIVE/'host/LpxAccuracy.h'),('previous_cpp',PRE/'LpxAccuracy.cpp'),('previous_h',PRE/'LpxAccuracy.h')]:
   if sha(path)!=EXPECTED[name]:raise AssertionError('Unexpected frozen Long input: '+name)
  cfg=REPO/'web-player/scripts/lib/lpx-build.mjs';text=cfg.read_text(encoding='utf-8')
  names=re.findall(r"'([^']+\.cpp)'",text.split('export const hostSources=host([')[1].split(']);')[0]);defines=re.findall(r"'([^']+)'",text.split('export const portableDefines=[')[1].split('];')[0])
  common=[ACTIVE/'src/Lpx4HybridCore.cpp',ACTIVE/'host/LpxEncoder.cpp',*(ACTIVE/'host'/n for n in names if n!='LpxAccuracy.cpp'),ACTIVE/'host/LpxAdaptiveApi.cpp']
  inputs=[*common,ACTIVE/'host/LpxAccuracy.cpp',PRE/'LpxAccuracy.cpp',PRE/'LpxAccuracy.h',HERE/'long.cpp',Path(__file__),HERE.parent/'PROTOCOL.md',HERE.parents[1]/'round2/tests/integration.cpp',cfg]
  for directory in (ACTIVE/'host',ACTIVE/'src'):inputs.extend(directory.glob('*.h'));inputs.extend(directory.glob('*.inc'))
  frozen={p.relative_to(REPO).as_posix():sha(p) for p in inputs};cls.receipt=dict(schema='lpx-audiobook-long-independent-v1',passed=False,expected=EXPECTED,sources=frozen,builds={},results={})
  flags=['-O2','-std=c++11','-ffp-contract=off',*('-D'+d for d in defines),'-include',native(ACTIVE/'host/LpxHostWorkspace.h'),'-I'+native(ACTIVE/'host'),'-I'+native(ACTIVE/'src')]
  cls.receipt['compiler']=subprocess.check_output(cls.prefix+['g++','--version'],text=True).splitlines()[0]
  objects=[];commands=[];objdir=OUTPUT/'objects';objdir.mkdir(exist_ok=True)
  for source in common:
   obj=objdir/(source.stem+'.o');command=['g++',*flags,'-c',native(source),'-o',native(obj)];built=subprocess.run(cls.prefix+command,capture_output=True,text=True)
   if built.returncode:raise AssertionError(built.stdout+built.stderr)
   objects.append(obj);commands.append(command)
  cls.receipt['common_commands']=commands
  for version in ('previous','long'):
   for enabled in (0,1):
    label=f'{version}-{enabled}';source=PRE/'LpxAccuracy.cpp' if version=='previous' else ACTIVE/'host/LpxAccuracy.cpp';binary=OUTPUT/label
    command=['g++',*flags,f'-DLPX_ENCODER_COMPACT_ENSEMBLE={enabled}',*(native(o) for o in objects),native(source),native(HERE/'long.cpp'),'-o',native(binary)]
    built=subprocess.run(cls.prefix+command,capture_output=True,text=True)
    if built.returncode:raise AssertionError(built.stdout+built.stderr)
    cls.receipt['builds'][label]=dict(command=command,binary_sha256=sha(binary),limit=64000 if version=='previous' else 160000)
  if frozen!={p.relative_to(REPO).as_posix():sha(p) for p in inputs}:raise AssertionError('Long inputs changed during compilation')
 @classmethod
 def tearDownClass(cls):
  cls.receipt['passed']=len(cls.receipt['results'])==6 and all(x['passed'] for x in cls.receipt['results'].values());(OUTPUT/'receipt.json').write_text(json.dumps(cls.receipt,indent=2)+'\n',encoding='utf-8')
 def check(self,mode,labels=('long-1',)):
  outputs={};passed=True
  for label in labels:
   before=time.monotonic();limit=self.receipt['builds'][label]['limit'];p=subprocess.run(self.prefix+[native(OUTPUT/label),mode,str(limit)],capture_output=True,text=True)
   outputs[label]=dict(returncode=p.returncode,stdout=p.stdout.strip(),stderr=p.stderr.strip(),wall_seconds=time.monotonic()-before);passed&=p.returncode==0 and 'PASS' in p.stdout
  def lines(label,prefix):return [s for s in outputs[label]['stdout'].splitlines() if s.startswith(prefix)]
  if mode=='automatic':
   passed&=lines('previous-0','ENCODE ')==lines('long-0','ENCODE ')
   passed&=[s for s in lines('previous-1','ENCODE ') if s.startswith('ENCODE 641 ')]==[s for s in lines('long-1','ENCODE ') if s.startswith('ENCODE 641 ')]
  if mode=='streaming':passed&=lines('long-0','STREAM ')==lines('long-1','STREAM ')
  if mode=='composition':
   passed&=all(lines(label,'FLOOR ')==lines('previous-0','FLOOR ') for label in labels)
   passed&=lines('previous-0','COMPOSE ')==lines('long-0','COMPOSE ')
   passed&=[s for s in lines('previous-1','COMPOSE ') if s.startswith('COMPOSE 1281 ')]==[s for s in lines('long-1','COMPOSE ') if s.startswith('COMPOSE 1281 ')]
  self.receipt['results'][mode]=dict(passed=bool(passed),outputs=outputs);self.assertTrue(passed,json.dumps(outputs,indent=2))
 def test_actual_long_header_large_payload_and_native_eof(self):self.check('geometry')
 def test_all_unchanged_scope_exclusions_and_new_boundaries(self):self.check('scope',('previous-0','previous-1','long-0','long-1'))
 def test_direct_long_old_selector_actual_B0_and_rollback(self):self.check('selection')
 def test_macro0_previous_identity_short_enabled_identity_and_c_abi(self):self.check('automatic',('previous-0','previous-1','long-0','long-1'))
 def test_real_carried_streaming_stays_excluded_and_identical(self):self.check('streaming',('long-0','long-1'))
 def test_reset_floor_and_full_automatic_composition_equivalence(self):self.check('composition',('previous-0','previous-1','long-0','long-1'))
if __name__=='__main__':unittest.main(verbosity=2)
