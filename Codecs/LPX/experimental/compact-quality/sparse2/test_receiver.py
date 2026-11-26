"""Tiny synthetic/native bridge checks; no encoder search or corpus execution."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

parser=argparse.ArgumentParser();parser.add_argument('--packages',type=Path)
parser.add_argument('--distro',default='Ubuntu');options,remaining=parser.parse_known_args()
if options.packages:sys.path.insert(0,str(options.packages.resolve()))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native_receiver import NativeReceiver,build_servers,OUTPUT,REPO,ACTIVE,HELLO,REQUEST,RESPONSE,launcher,linux_path
sys.path.insert(0,str(ACTIVE/'tools'))
sys.path.insert(0,str(REPO/'Codecs/LPX/research/low-bitrate-speech-2026-11-02'))
import numpy as np
import speech_sparse80 as sparse
import speech_compact as compact
from standard_metrics import pwm_duties


def fixture(n,static=False,pre=8192,bright=4096):
    frames=(n+319)//320
    spectra=[[3+5*j+(0 if static else f%2) for j in range(10)] for f in range(frames)]
    parameters=[(12+f%3,[18,37,145][f%3],[0,6,14][f%3]) for f in range(frames)]
    pulses=[(sparse.POSITIONS[(i*13)%64],-8 if i%2 else 7) for i in range(frames*4)]
    return sparse.pack(n,spectra,parameters,pulses,pre,bright)


class ReceiverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build=build_servers(distro=options.distro)
        cls.receivers=[NativeReceiver(kind,distro=options.distro) for kind in ('common','v5-only')]
        cls.results={}

    @classmethod
    def tearDownClass(cls):
        for receiver in cls.receivers:
            receiver.close()
            if receiver.process.returncode!=0:raise AssertionError('Native receiver failed clean EOF shutdown')
        receipt=dict(schema='lpx-sparse2-native-ipc-tests-v1',python=sys.version.split()[0],numpy=np.__version__,
                     sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*') if p.is_file()},
                     build=cls.build,results=cls.results,
                     requests={receiver.kind:receiver.calls for receiver in cls.receivers})
        (OUTPUT/'tests.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')

    def test_synthetic_sparse80_model_native_pcm_pwm_metadata_and_tails(self):
        cases=0
        for n in (1,19,20,21,39,40,41,79,80,81,159,160,161,319,320,321,641,1281):
          for pre,bright in ((0,0),(8192,4096)):
            blob=fixture(n,pre=pre,bright=bright);bridge=sparse.expand(blob)
            model=sparse.decode_model(blob);duty=pwm_duties(model)
            for receiver in self.receivers:
                actual,meta=receiver.decode_result(bridge,n,s16=True)
                np.testing.assert_array_equal(actual,model)
                np.testing.assert_array_equal(receiver.decode_one(bridge,n),duty)
                self.assertEqual(actual.dtype,np.dtype('int16'))
                self.assertEqual((meta['status'],meta['decoded_samples'],meta['declared_samples'],meta['produced_samples']),
                                 (0,n,n,n))
                self.assertEqual((meta['sample_rate'],meta['error'],meta['finished'],meta['payload_bytes']),
                                 (8000,0,True,n*2))
            cases+=1
        self.results['model_native']=dict(synthetic_cases=cases,common_and_v5_only_pcm_pwm_exact=True,
                                         tails_and_metadata_exact=True)

    def test_invalid_streams_are_none_and_persistent_receivers_recover(self):
        original=fixture(641);bridge=sparse.expand(original);model=sparse.decode_model(original)
        invalid=[b'',b'bad',bridge[:19],bridge[:-1],bridge+b'\0',original]
        for at,width,value in ((0,1,0),(4,1,99),(5,1,15),(6,2,16001),(8,4,0),(12,2,16385)):
            bad=bytearray(bridge);bad[at:at+width]=value.to_bytes(width,'little');invalid.append(bytes(bad))
        fields=compact.unpack(bridge);_,meta=compact.pack(*fields[:7],extras=fields[7])
        padding=None
        if meta['payload_bits']%8:
            bad=bytearray(bridge);bad[-1]|=128;padding=bytes(bad)
            with self.assertRaises(ValueError):compact.unpack(padding)
        for receiver in self.receivers:
            pid=receiver.process.pid
            for index,bad in enumerate(invalid):
                for s16 in (False,True):
                    actual,meta=receiver.decode_result(bad,641,s16=s16)
                    self.assertTrue(actual is None,f'{receiver.kind} invalid case{index} returned success metadata{meta}')
                    self.assertLess(meta['status'],0);self.assertEqual(meta['payload_bytes'],0)
                np.testing.assert_array_equal(receiver.decode_one_s16(bridge,641),model)
            self.assertIsNone(receiver.decode_one_s16(bridge,640))
            self.assertIsNone(receiver.decode_one(bridge,642))
            for n in (-1,1000001,1.5,True):
                with self.assertRaises(ValueError):receiver.decode_one(bridge,n)
            with self.assertRaises(ValueError):receiver.decode_one(b'\0'*65536,641)
            self.assertEqual(receiver.process.pid,pid);self.assertIsNone(receiver.process.poll())
            np.testing.assert_array_equal(receiver.decode_one_s16(bridge,641),model)
            if padding is not None:
                # Preserve the old native receiver contract: unused final bits
                # are ignored. Strict source parsing belongs to the Python
                # unpack/model layer already run before native admission.
                np.testing.assert_array_equal(receiver.decode_one_s16(padding,641),model)
                np.testing.assert_array_equal(receiver.decode_one(padding,641),pwm_duties(model))
        self.results['invalid_streams']=dict(cases=len(invalid),both_domains=True,recovered_without_process_restart=True,
                                             native_padding_tolerated=padding is not None,strict_python_padding_rejected=padding is not None)

    def test_batch_interface_interleaving_and_existing_admission_baseline(self):
        from concurrent.futures import ThreadPoolExecutor
        blob=fixture(3201,static=True);bridge=sparse.expand(blob);model=sparse.decode_model(blob)
        self.assertLessEqual(len(blob),3201*2//64)
        for receiver in self.receivers:
            results=receiver.decode_many_s16([bridge,b'bad',bridge],3201)
            np.testing.assert_array_equal(results[0],model);self.assertIsNone(results[1]);np.testing.assert_array_equal(results[2],model)
            self.assertEqual(receiver.decode_many([],3201),[])
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda i:self.receivers[i%2].decode_one_s16(bridge,3201),range(8)))
        for actual in results:np.testing.assert_array_equal(actual,model)
        from round_admission import RoundAdmission
        # Constructor validates ONLY this synthetic protected baseline; no new
        # candidate/operator is generated, searched or admitted in this check.
        output=Path(tempfile.mkdtemp(prefix='synthetic-admission-',dir=OUTPUT))/'round'
        admission=RoundAdmission(model,blob,output,*self.receivers,speech=False)
        self.assertEqual(len(admission.rows),1)
        self.assertTrue(admission.rows[0]['native_common_and_v5_only_pcm_pwm_exact'])
        self.results['compatibility']=dict(batch_none_contract=True,interleaved_requests=8,
                                           existing_round_admission_baseline_exact=True,synthetic_bytes=len(blob))

    def test_transport_eof_partial_header_partial_payload_and_bad_frame(self):
        binary=Path(self.build['variants']['common']['binary'])
        frames=[(b'',0),(b'LP',2),(REQUEST.pack(0x3144504c,1,0,10,1,0)+b'12',2),
                (REQUEST.pack(0,1,0,0,0,0),3),(REQUEST.pack(0x3144504c,1,0,65536,1,0),3)]
        for payload,expected in frames:
            child=subprocess.Popen(launcher(options.distro)+[linux_path(binary)],stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual(HELLO.unpack(child.stdout.read(HELLO.size)),(0x5348504c,1,0,5,0))
            out,err=child.communicate(input=payload,timeout=10)
            self.assertEqual(child.returncode,expected);self.assertEqual(out,b'');self.assertEqual(err,b'')
        self.results['transport']=dict(cases=len(frames),bounded_frame_validation=True,clean_eof=True)


if __name__=='__main__':unittest.main(argv=[__file__,*remaining],verbosity=2)
