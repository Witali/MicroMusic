"""Existing numerical/proposal controls and searched old/default byte identity.

Linux/WSL only, standard library. Builds immutable source snapshots under ignored
build/. Baseline comes from local Git 3c0cd974; no ref/index/worktree is changed.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[4]
ACTIVE=REPO/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
RUN_ROOT=REPO/'build/pcm-quality-existing-regressions'
OUTPUT=RUN_ROOT
BASELINE='3c0cd974'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command):
    result=subprocess.run(list(map(str,command)),capture_output=True)
    if result.returncode:
        raise AssertionError(' '.join(map(str,command))+'\n'+result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace'))
    return result.stdout


class QualityTargetExistingRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global OUTPUT
        RUN_ROOT.mkdir(parents=True,exist_ok=True)
        OUTPUT=Path(tempfile.mkdtemp(prefix='run-',dir=RUN_ROOT))
        config=(REPO/'web-player/scripts/lib/lpx-build.mjs').read_text()
        cls.names=re.findall(r"'([^']+\.cpp)'",config.split('export const hostSources=host([')[1].split(']);')[0])
        cls.defines=['-D'+s for s in re.findall(r"'([^']+)'",config.split('export const portableDefines=[')[1].split('];')[0])]
        cls.flags=['-O3','-std=c++11','-ffp-contract=off',*cls.defines]
        cls.receipt=dict(baseline_revision=BASELINE,compiler=run(['g++','--version']).decode().splitlines()[0],builds={},results={})
        # Snapshot current inputs to avoid interleaved compiler reads while
        # other agents work on unrelated API/docs files.
        current=OUTPUT/'current/Codecs/LPX/01_ACTIVE_Q0_CODEC'
        for folder in ('src','host'):
            before={p.relative_to(ACTIVE/folder).as_posix():sha(p) for p in (ACTIVE/folder).rglob('*') if p.is_file()}
            shutil.copytree(ACTIVE/folder,current/folder)
            if before!={p.relative_to(ACTIVE/folder).as_posix():sha(p) for p in (ACTIVE/folder).rglob('*') if p.is_file()}:
                raise RuntimeError('Current inputs changed during snapshot')
            if before!={p.relative_to(current/folder).as_posix():sha(p) for p in (current/folder).rglob('*') if p.is_file()}:
                raise RuntimeError('Snapshot differs from current inputs')
        git=REPO.parent.parent/'.git' if REPO.parent.name=='.worktree' else REPO/'.git'
        archive=run(['git','--git-dir='+str(git),'archive',BASELINE,'--',
                     'Codecs/LPX/01_ACTIVE_Q0_CODEC/src','Codecs/LPX/01_ACTIVE_Q0_CODEC/host'])
        baselineRoot=OUTPUT/'baseline'
        baselineRoot.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for member in tar.getmembers():
                target=(baselineRoot/member.name).resolve()
                if baselineRoot.resolve() not in target.parents or not (member.isdir() or member.isfile()):
                    raise RuntimeError('Unexpected archive member')
            tar.extractall(baselineRoot,filter='data')
        old=baselineRoot/'Codecs/LPX/01_ACTIVE_Q0_CODEC'
        cls.currentObjects=cls.objects(current,'current')
        cls.oldObjects=cls.objects(old,'baseline')
        cls.current=current
        for name in ('profile_quality','pitch_guard','spectral_pulses'):
            cls.link(current,cls.currentObjects,ACTIVE/'tests'/f'{name}.cpp',OUTPUT/name)
        driver=ACTIVE/'tests/quality_target_legacy.cpp'
        cls.link(current,cls.currentObjects,driver,OUTPUT/'legacy-current',['-DLPX_POLICY_CURRENT=1'])
        cls.link(old,cls.oldObjects,driver,OUTPUT/'legacy-baseline')

    @classmethod
    def objects(cls,active,label):
        sources=[active/'src/Lpx4HybridCore.cpp',active/'host/LpxEncoder.cpp',
                 *(active/'host'/name for name in cls.names),active/'host/LpxAdaptiveApi.cpp']
        directory=OUTPUT/label/'objects';directory.mkdir()
        def compile_one(source):
            target=directory/(source.stem+'.o')
            command=['g++',*cls.flags,'-include',active/'host/LpxHostWorkspace.h',
                     '-I'+str(active/'src'),'-I'+str(active/'host'),'-c',source,'-o',target]
            run(command)
            return target
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(compile_one,sources))
        cls.receipt['builds'][label]=dict(flags=cls.flags,sources={p.relative_to(active).as_posix():sha(p) for p in sources})
        return result

    @classmethod
    def link(cls,active,objects,source,target,extra=()):
        run(['g++',*cls.flags,*extra,'-include',active/'host/LpxHostWorkspace.h',
             '-I'+str(active/'src'),'-I'+str(active/'host'),source,*objects,'-o',target])

    @classmethod
    def tearDownClass(cls):
        (OUTPUT/'receipt.json').write_text(json.dumps(cls.receipt,indent=2)+'\n',encoding='utf-8')
        (RUN_ROOT/'latest-run.json').write_text(json.dumps({'output':OUTPUT.relative_to(REPO).as_posix()},indent=2)+'\n',encoding='utf-8')

    def test_existing_profile_quality(self):
        self.receipt['results']['profile_quality']=run([OUTPUT/'profile_quality']).decode().strip()

    def test_existing_actual_rate_pitch_guard(self):
        self.receipt['results']['pitch_guard']=run([OUTPUT/'pitch_guard']).decode().strip()

    def test_existing_spectral_pulse_profiles_rates_and_long_tails(self):
        self.receipt['results']['spectral_pulses']=run([OUTPUT/'spectral_pulses']).decode().strip()

    def test_searched_default_bytes_match_old_legacy_adaptive_and_strict_three_k(self):
        for mode in ('adaptive','three-k'):
            with self.subTest(mode=mode):
                before=run([OUTPUT/'legacy-baseline',mode])
                default=run([OUTPUT/'legacy-current',mode])
                explicit=run([OUTPUT/'legacy-current',mode,'pwm'])
                self.assertGreater(len(before),13)
                self.assertEqual(default,before)
                self.assertEqual(explicit,before)
                self.receipt['results'][mode]=dict(bytes=len(before),sha256=hashlib.sha256(before).hexdigest(),
                    calls=1,old_default_byte_exact=True,explicit_pwm_byte_exact=True)


if __name__=='__main__':
    unittest.main(verbosity=2)
