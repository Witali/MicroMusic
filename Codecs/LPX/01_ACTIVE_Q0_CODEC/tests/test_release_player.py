import json,os,subprocess,tempfile,unittest
from pathlib import Path
from build_release_player import REPOSITORY,guard,validate
class ReleasePlayerTests(unittest.TestCase):
    def valid(self,n=3):
        return dict(stopped=1,eof=1,decoder_error=0,observer_errors=0,observer_exit_code=0,underruns=0,
                    timer_ticks=n,timer_events=n,produced=n,played=n,queued_at_stop=0,timer_started=1,stack_margin_all_bytes=100)
    def test_external_evidence_requires_output_ticks_eof_and_no_underrun(self):
        pwm=b'\x80\x7f\x81';report=self.valid()
        self.assertTrue(validate(report,pwm,pwm))
        for field,value in (('stopped',0),('eof',0),('decoder_error',3),('observer_errors',1),('observer_exit_code',7),
                            ('underruns',1),('timer_ticks',4),('timer_events',2),('produced',4),('played',2),
                            ('queued_at_stop',1),('timer_started',0),('stack_margin_all_bytes',0),('stopped',True)):
            bad=dict(report);bad[field]=value
            with self.subTest(field=field,value=value):self.assertFalse(validate(bad,pwm,pwm))
        self.assertFalse(validate(report,pwm[:-1],pwm));self.assertFalse(validate(report,pwm[::-1],pwm))
        self.assertFalse(validate(None,pwm,pwm));self.assertFalse(validate(report,None,None))
    def test_explicit_failure_is_distinct_from_successful_empty_playback(self):
        bad=self.valid(0);bad.update(decoder_error=1,timer_started=0)
        self.assertTrue(validate(bad,b'',b'',expected_error=1))
        self.assertFalse(validate(bad,b'',b''))
        self.assertFalse(validate(bad,b'',b'',expected_error=True))
    def test_outputs_cannot_alias_inputs_or_escape_build(self):
        build=REPOSITORY/'build';build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build) as temporary:
            folder=Path(temporary).resolve();self.assertTrue(folder.is_relative_to(build.resolve()))
            source=folder/'input';source.write_bytes(b'preserve')
            output=folder/'output';output.mkdir()
            os.link(source,output/'cost.json')
            with self.assertRaises(ValueError):guard(output,[source])
            (output/'cost.json').unlink();os.link(source,output/'verification.writing')
            with self.assertRaises(ValueError):guard(output,[source])
            self.assertEqual(source.read_bytes(),b'preserve')
        with self.assertRaises(ValueError):guard(REPOSITORY/'outside-build')
        with self.assertRaises(ValueError):guard(build)
@unittest.skipUnless(os.environ.get('LPX_PLAYER_TEST_ARTIFACTS'), 'Optional external-observer integration inputs are absent')
class ReleaseObserverMetadataTests(unittest.TestCase):
    def test_descriptor_is_checked_before_simulated_memory_access(self):
        from profile_avr import linux_path
        artifacts=Path(os.environ['LPX_PLAYER_TEST_ARTIFACTS']).resolve()
        runner=Path(os.environ['LPX_PLAYER_TEST_OBSERVER']).resolve()
        library=Path(os.environ['LPX_PLAYER_TEST_LIB']).resolve()
        wsl=os.environ.get('LPX_PLAYER_TEST_WSL')
        values=[int(v) for v in (artifacts/'observer.txt').read_text().split()]
        self.assertEqual(len(values),27)
        malformed=[]
        for index in range(27):
            for value in (0,4294967295):
                bad=list(values);bad[index]=value
                malformed.append(('field-'+str(index)+'-'+str(value),' '.join(map(str,bad)).encode()))
        bad=list(values);bad[20],bad[21]=bad[21],bad[20]
        malformed.append(('swapped-state',' '.join(map(str,bad)).encode()))
        bad=list(values);bad[17]=bad[16]
        malformed.append(('prefill-at-capacity',' '.join(map(str,bad)).encode()))
        bad=list(values);bad[16]=256;bad[17]=192;bad[18]=1
        malformed.append(('wrong-elf-queue',' '.join(map(str,bad)).encode()))
        valid=' '.join(map(str,values)).encode()
        malformed += [('empty',b''),('negative',b'-1 '+valid),('overflow',b'4294967296 '+valid),
                      ('trailing',valid+b' 1'),('short',b'1 2'),('nul',valid+b'\x00'),
                      ('long',b'1 '*1024),('sign',b'+1 '+valid)]
        with tempfile.TemporaryDirectory(dir=REPOSITORY/'build') as temporary:
            folder=Path(temporary)
            def run(metadata):
                sidecar=folder/'observer.txt';sidecar.write_bytes(metadata)
                outputs=[folder/'valid.pcm8',folder/'observer.json']
                for path in outputs:path.unlink(missing_ok=True)
                args=[runner,artifacts/'player.elf',*outputs,sidecar]
                if wsl:
                    command=['wsl','-d',wsl,'--','env','LD_LIBRARY_PATH='+linux_path(library),*[linux_path(p) for p in args]]
                    result=subprocess.run(command,capture_output=True,timeout=20)
                else:
                    env=os.environ.copy();env['LD_LIBRARY_PATH']=str(library)
                    result=subprocess.run([str(p) for p in args],env=env,capture_output=True,timeout=20)
                return result,outputs
            result,outputs=run(valid)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            self.assertEqual(json.loads(outputs[1].read_text())['observer_errors'],0)
            for name,metadata in malformed:
                with self.subTest(descriptor=name):
                    result,outputs=run(metadata)
                    self.assertEqual(result.returncode,2,result.stderr.decode(errors='replace'))
                    self.assertFalse(any(p.exists() for p in outputs))
if __name__=='__main__':unittest.main()
