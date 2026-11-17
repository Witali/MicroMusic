"""Actual-rate WAV encoding and universal v9 header/timer build contracts.

Scientific Python dependencies match the existing encoder. A C++ compiler is
required; LPX_TEST_WSL selects its WSL distribution on Windows.
"""
import contextlib
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tests')]
import build_attiny88_player as builder
import speech_compact
import speech_v4
import speech_v9
from speech_v9_audio import (SAMPLE_RATES,ProcessReference,decode_pcm,encode_pcm,
    main,metadata,validate_rate)
from wav_lpc import load_wav
from test_sram512_profile import fixture


class SampleRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context=contextlib.ExitStack()
        cls.legacy=cls.context.enter_context(ProcessReference(5,wsl=os.environ.get('LPX_TEST_WSL')))
        cls.v9=cls.context.enter_context(ProcessReference(9,wsl=os.environ.get('LPX_TEST_WSL')))

    @classmethod
    def tearDownClass(cls):cls.context.close()

    def test_repack_preserves_rate_and_legacy_stays8k(self):
        original=speech_v9.repack(fixture(6,17,145,'changing',True))[0]
        for rate in SAMPLE_RATES:
            data=bytearray(original);struct.pack_into('<H',data,3,rate)
            self.assertEqual(speech_v9.repack(data)[0],data)
            self.assertEqual(metadata(data)['sample_rate'],rate)
            pcm,info=decode_pcm(data,self.v9)
            self.assertEqual(len(pcm),17)
            if rate!=8000:
                with self.assertRaises(ValueError):speech_v9.repack(data,5)

    def test_unsupported_rate_rejected_by_metadata_and_c(self):
        original=speech_v9.repack(fixture(4,17,145,'changing',True))[0]
        for rate in (0,1,7999,8001,11025,11999,12001,15999,16001,65535):
            data=bytearray(original);struct.pack_into('<H',data,3,rate)
            with self.subTest(rate=rate),self.assertRaises(ValueError):metadata(data)
            self.assertIsNone(self.v9.decode_one(data,17))
        for rate in (True,8000.,'12000',32000):
            with self.assertRaises(ValueError):validate_rate(rate)

    def test_compatibility_selection_retains8k_only_c_receiver(self):
        receiver=ProcessReference(9,wsl=os.environ.get('LPX_TEST_WSL'))
        receiver.compiler+=['-DLPX4_EXTENDED_SAMPLE_RATES=0']
        data=bytearray(speech_v9.repack(fixture(6,17,145,'changing',True))[0])
        with receiver as compatibility:
            for rate in SAMPLE_RATES:
                struct.pack_into('<H',data,3,rate)
                result=compatibility.decode_one_s16(data,17)
                if rate==8000:self.assertIsNotNone(result)
                else:self.assertIsNone(result)

    def test_compile_time_c_receiver_checks_the_selected_file_rate(self):
        data=bytearray(speech_v9.repack(fixture(6,17,145,'changing',True))[0])
        for selected in SAMPLE_RATES:
            receiver=ProcessReference(9,wsl=os.environ.get('LPX_TEST_WSL'))
            receiver.compiler+=[f'-DLPX4_SAMPLE_RATE={selected}']
            with receiver as fixed:
                for rate in SAMPLE_RATES:
                    struct.pack_into('<H',data,3,rate)
                    actual=fixed.decode_one_s16(data,17)
                    if rate==selected:
                        np.testing.assert_array_equal(actual,self.v9.decode_one_s16(data,17))
                    else:self.assertIsNone(actual)

    def test_real_source_resampling_and_header_rate_wav(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);source=folder/'input.wav'
            x=np.rint(7000*np.sin(np.arange(960)*2*np.pi*733/24000)).astype('<i2')
            with wave.open(str(source),'wb') as out:
                out.setparams((1,2,24000,len(x),'NONE','not compressed'));out.writeframes(x.tobytes())
            old,_=load_wav(source)
            same,_=load_wav(source,sample_rate=8000)
            np.testing.assert_array_equal(old,same)
            for rate in SAMPLE_RATES:
                reference,_=load_wav(source,sample_rate=rate)
                self.assertEqual(len(reference),960*rate//24000)
                blob,pcm,report=encode_pcm(reference,4,self.legacy,self.v9,sample_rate=rate)
                self.assertEqual(metadata(blob)['sample_rate'],rate)
                self.assertEqual(report['packet_ms'],320000/rate)
                self.assertEqual(report['file_bitrate_bps'],len(blob)*8*rate/len(reference))
                target=folder/f'decoded-{rate}.wav'
                args=['decode',str(folder/'audio.lpx'),str(target)]
                if os.environ.get('LPX_TEST_WSL'):args+=['--wsl',os.environ['LPX_TEST_WSL']]
                (folder/'audio.lpx').write_bytes(blob)
                with contextlib.redirect_stdout(io.StringIO()):main(args)
                with wave.open(str(target),'rb') as inp:
                    self.assertEqual(inp.getframerate(),rate)
                    self.assertEqual(inp.getnframes(),len(reference))
                    self.assertEqual(inp.readframes(len(reference)),pcm.astype('<i2').tobytes())
            args=['encode',str(source),str(folder/'encoded'),'--profile','6','--sample-rate','16000']
            if os.environ.get('LPX_TEST_WSL'):args+=['--wsl',os.environ['LPX_TEST_WSL']]
            with contextlib.redirect_stdout(io.StringIO()):report=main(args)
            self.assertEqual(report['sample_rate'],16000)
            self.assertEqual(report['samples'],640)
            self.assertTrue(report['native_model_exact'])
            with wave.open(str(folder/'encoded/decoded.wav'),'rb') as inp:self.assertEqual(inp.getframerate(),16000)

    def test_8k_payload_matches_unchanged_search(self):
        t=np.arange(321)/8000
        reference=np.rint(5000*np.sin(2*np.pi*213*t)+1700*np.sin(2*np.pi*871*t)).astype(np.int16)
        for profile in (4,6):
            old,expected,_=speech_v4.encode(reference,profile,self.legacy)
            previous=speech_v9.repack(speech_compact.repack(old)[0])[0]
            current,pcm,_=encode_pcm(reference,profile,self.legacy,self.v9)
            self.assertEqual(previous,current)
            np.testing.assert_array_equal(expected,pcm)

    def test_uniform_and_mixed_stream_validation(self):
        data=bytearray(speech_v9.repack(fixture(6,17,145,'changing',True))[0])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);paths=[]
            for rate in SAMPLE_RATES:
                struct.pack_into('<H',data,3,rate)
                path=p/f'{rate}.lpx';path.write_bytes(data);paths.append(path)
            output=builder.REPO/'build'/f'test-rate-invalid-{os.getpid()}'
            for bad in ([paths[0],paths[1]],[paths[1],paths[2]]):
                with self.assertRaisesRegex(ValueError,'one common sampling rate'):
                    builder.build(bad,output)
            for path in paths[1:]:
                with self.assertRaisesRegex(ValueError,'does not match the build sampling rate'):
                    builder.build(path,output)
            for rate in (0,True,8000.,11025):
                with self.assertRaisesRegex(ValueError,'Select a build sampling rate'):
                    builder.build(paths[0],output,sample_rate=rate)
            for flag in ('-DLPX4_SAMPLE_RATE=12000','-ULPX4_SAMPLE_RATE',
                         '-DLPX25_HEADER_SAMPLE_RATE=1','-DLPX4_EXTENDED_SAMPLE_RATES=0'):
                with self.assertRaisesRegex(ValueError,'Use sample_rate'):
                    builder.build(paths[0],output,extra_flags=[flag])

    def test_truncated_and_bad_v9_are_rejected(self):
        data=speech_v9.repack(fixture(6,17,145,'changing',True))[0]
        for broken in (data[:12],data[:-1],data+b'\0',b'L8'+data[2:]):
            with self.subTest(length=len(broken)),self.assertRaises(ValueError):metadata(broken)


if __name__=='__main__':unittest.main()
