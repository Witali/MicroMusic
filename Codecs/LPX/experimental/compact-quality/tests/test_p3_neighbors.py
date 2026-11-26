"""Independent tests for the registered two-site P3 neighbor experiment.

Builds a separate fixed reference and generated variant; never modifies the
production source or the frozen original local-trace tests/receipts.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[4]
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
OUTPUT=REPO/'build/compact-quality/p3-neighbor-independent'
parser=argparse.ArgumentParser()
parser.add_argument('--variant',type=Path,default=REPO/'build/compact-quality/LpxLpcRefine.p3-grid.cpp')
OPTIONS,remaining=parser.parse_known_args()
BASE_HASH='cba09bfaab7092612befeab2e2f5af9304787ad7131efa88740bcb58abb1f8a7'
VARIANT_HASH='b37f6a8d16b969ad1af97350431ed9630cfdc496146d5fbdc5c30961397ac87b'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def native(path):
    path=Path(path).resolve()
    if os.name=='nt' and os.environ.get('LPX_TEST_WSL'):
        return '/mnt/'+path.drive[0].lower()+'/'+('/'.join(path.parts[1:]))
    return str(path)


def checked_variant(base,variant):
    old=base.read_bytes();new=variant.read_bytes()
    if digest(base)!=BASE_HASH or digest(variant)!=VARIANT_HASH:raise AssertionError('Unexpected experiment source hash')
    # Independent reconstruction of the two registered changes, including the
    # original non-P3 -1,+1 order; all remaining bytes must be identical.
    replacements=[
        (b'for(int field=0;field<10;++field)for(int delta:{-1,1}) {',
         b'for(int field=0;field<10;++field)for(int move=0;move<(input.accuracy==3?4:2);++move) {\n'
         b'            const int delta=input.accuracy==3?(move==0?-4:move==1?-2:move==2?2:4):(move?1:-1);'),
        (b'if(single.spectra[first][k]!=anchor.spectra[first][k])\n'
         b'            fields+=std::abs(single.spectra[first][k]-anchor.spectra[first][k])==1?1:100;',
         b'if(single.spectra[first][k]!=anchor.spectra[first][k]) {\n'
         b'            const int distance=std::abs(single.spectra[first][k]-anchor.spectra[first][k]);\n'
         b'            fields+=(anchor.accuracy==3?(distance==2||distance==4):distance==1)?1:100;\n'
         b'        }')]
    for before,after in replacements:
        if old.count(before)!=1:raise AssertionError('Unexpected checked patch site count')
        old=old.replace(before,after)
    if old!=new:raise AssertionError('Override has changes outside the exact registered two-site patch')


class NeighborTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True,exist_ok=True)
        cls.prefix=['wsl','-d',os.environ['LPX_TEST_WSL'],'--'] if os.name=='nt' and os.environ.get('LPX_TEST_WSL') else []
        base=ACTIVE/'host/LpxLpcRefine.cpp';variant=OPTIONS.variant.resolve();checked_variant(base,variant)
        config=(REPO/'web-player/scripts/lib/lpx-build.mjs').read_text(encoding='utf-8')
        names=re.findall(r"'([^']+\.cpp)'",config.split('export const hostSources=host([')[1].split(']);')[0])
        defines=re.findall(r"'([^']+)'",config.split('export const portableDefines=[')[1].split('];')[0])
        sources=[ACTIVE/'src/Lpx4HybridCore.cpp',ACTIVE/'host/LpxEncoder.cpp',
                 *(ACTIVE/'host'/name for name in names if name!='LpxLpcRefine.cpp'),HERE/'p3_neighbors.cpp']
        inputs=[*sources,base,variant,HERE/'local_trace.cpp',*(ACTIVE/'host').glob('*.h'),*(ACTIVE/'src').glob('*.h'),
                *(ACTIVE/'host').glob('*.inc'),*(ACTIVE/'src').glob('*.inc')]
        before={p.relative_to(REPO).as_posix():digest(p) for p in inputs}
        def build(item):
            name,implementation=item;binary=OUTPUT/name
            command=['g++','-O2','-std=c++11','-ffp-contract=off',*('-D'+d for d in defines),
                     '-DLPX_LPC_REFINE_SOURCE="'+native(implementation)+'"',
                     '-include',native(ACTIVE/'host/LpxHostWorkspace.h'),'-I'+native(ACTIVE/'host'),'-I'+native(ACTIVE/'src'),
                     *(native(p) for p in sources),'-o',native(binary)]
            done=subprocess.run(cls.prefix+command,capture_output=True,text=True)
            if done.returncode:raise AssertionError(done.stdout+done.stderr)
            return name,dict(command=command,binary_sha256=digest(binary),bytes=binary.stat().st_size)
        with ThreadPoolExecutor(max_workers=2) as pool:builds=dict(pool.map(build,[('reference',base),('variant',variant)]))
        if before!={p.relative_to(REPO).as_posix():digest(p) for p in inputs}:raise RuntimeError('Test inputs changed during build')
        cls.receipt=dict(schema='lpx-p3-neighbor-independent-v1',compiler=subprocess.check_output(cls.prefix+['g++','--version'],text=True).splitlines()[0],
                         exact_checked_patch_sites=2,sources=before,builds=builds,results={})

    @classmethod
    def tearDownClass(cls):
        (OUTPUT/'receipt.json').write_text(json.dumps(cls.receipt,indent=2)+'\n',encoding='utf-8')

    def run_native(self,build,mode,expected=0,diagnostic=None):
        done=subprocess.run(self.prefix+[native(OUTPUT/build),mode],capture_output=True,text=True)
        self.receipt['results'][build+'/'+mode]=dict(returncode=done.returncode,stdout=done.stdout.strip(),stderr=done.stderr.strip())
        self.assertEqual(done.returncode,expected,done.stdout+done.stderr)
        self.assertIn(diagnostic or 'PASS',done.stderr if expected else done.stdout)
        return done.stdout

    def test_legal_composition_and_illegal_context_guards(self):
        self.run_native('reference','composition',1,'legal P3 magnitude2/4 singles were not composable')
        self.run_native('variant','composition')

    def test_exact_reachable_neighborhood_and_work_bounds(self):
        self.run_native('reference','generator',1,'exact legal four-delta P3 neighborhood')
        self.run_native('variant','generator')

    def test_canonical_noops_native_audio_and_true_continuation(self):
        self.run_native('variant','reachable')

    def test_non_p3_complete_proposals_and_native_controls_unchanged(self):
        self.assertEqual(self.run_native('reference','controls'),self.run_native('variant','controls'))


if __name__=='__main__':unittest.main(argv=[__file__,*remaining],verbosity=2)
