"""Pure case/span/metadata contracts; no fitting, native build or image job."""
from collections import Counter
from pathlib import Path
import tempfile
import unittest

from native_inputs import Inputs,sha,verify_meta
from prepare_cases import (FIRST_OFFSET,IMAGE_BYTES,build_case,choose,descriptors,
    gates,image_layout,planned_rows,write_image)


def scratch():
    root=Path(__file__).resolve().parents[5]/'build/spi-case-contracts'
    root.mkdir(parents=True,exist_ok=True)
    return tempfile.TemporaryDirectory(dir=root)


class CaseContracts(unittest.TestCase):
    def test_24bit_offsets_and_uint16_stored_sizes(self):
        self.assertGreater(FIRST_OFFSET,65535)
        self.assertEqual(image_layout([22,65535,23]),[FIRST_OFFSET,FIRST_OFFSET+22,FIRST_OFFSET+22+65535])
        for sizes in ([],[21],[65536],[True],[65535]*255):
            with self.assertRaises(ValueError):
                image_layout(sizes)

    def test_exact_ff_image_preserves_full_stored_spans(self):
        with scratch() as temporary:
            path=Path(temporary)/'flash.bin'
            blobs=(b'a'*22,b'b'*31)
            offsets,digest=write_image(path,blobs)
            raw=path.read_bytes()
            self.assertEqual(len(raw),IMAGE_BYTES)
            self.assertEqual(sha(raw),digest)
            self.assertEqual(raw[:FIRST_OFFSET],b'\xff'*FIRST_OFFSET)
            self.assertEqual(raw[offsets[0]:offsets[1]],blobs[0])
            self.assertEqual(raw[offsets[1]:offsets[1]+31],blobs[1])
            self.assertEqual(raw[offsets[1]+31:],b'\xff'*(IMAGE_BYTES-offsets[1]-31))
            with self.assertRaises(FileExistsError):
                write_image(path,blobs)

    def test_fixed_28_rows_and_no_long_c_or_rom_job(self):
        chains=[dict(id='long-%03d'%i,kind='long') for i in range(1,7)]
        chains.extend(dict(id='short-p%d'%p,kind='short') for p in (4,6))
        rows=planned_rows(chains)
        self.assertEqual(len({r['id'] for r in rows}),28)
        long=[r for r in rows if r['chain_id'].startswith('long-')]
        self.assertEqual(len(long),12)
        self.assertTrue(all(r['storage']=='spi' and r['assembly'] for r in long))
        short=[r for r in rows if r not in long]
        self.assertEqual(Counter(r['storage'] for r in short),{'spi':8,'rom':8})
        self.assertEqual(Counter(r['extra_irq_cycles'] for r in rows),{0:14,100:14})

    def test_requested_bytes_allow_an_unread_final_packet_tail(self):
        self.assertEqual(verify_meta([1,0,160,160,1,30,30,0],160,1,40),30)
        self.assertEqual(verify_meta([1,0,160,160,1,0,0,0],160,0,40),0)
        for meta in ([1,0,160,160,0,30,30,0],[1,0,160,160,1,41,41,0],
                     [1,0,160,160,1,31,30,0],[1,1,160,160,1,30,30,0]):
            with self.assertRaises(AssertionError):
                verify_meta(meta,160,1,40)

    def test_binding_detects_mutated_source_and_wrong_size(self):
        with scratch() as temporary:
            path=Path(temporary)/'source.l4hy';path.write_bytes(b'a'*22)
            inputs=Inputs();inputs.read(path)
            with self.assertRaises(ValueError):
                inputs.stream(dict(path=str(path),stream_sha256=sha(path.read_bytes()),file_bytes=23))
            path.write_bytes(b'b'*22)
            with self.assertRaises(ValueError):
                inputs.verify()

    def test_whole_gate_reconstruction_keeps_f0_and_clipping(self):
        old=dict(metrics={d:dict(error_energy=100,stoi=.8) for d in ('pcm16','pwm8')},
            clipped_samples=0,voice=dict(within_tolerance_frames=3),pwm_voice=dict(within_tolerance_frames=3),score=1.)
        self.assertTrue(all(gates(old,old).values()))
        self.assertFalse(all(gates({**old,'voice':dict(within_tolerance_frames=2)},old).values()))
        self.assertFalse(all(gates({**old,'clipped_samples':1},old).values()))
        value={**old,'metrics':{d:dict(error_energy=99,stoi=.7) for d in ('pcm16','pwm8')}}
        self.assertFalse(gates(value,old)['old_pcm_pwm_floors_passed'])

    def test_budget_ties_raw_only_and_no_fit_are_explicit(self):
        rows=[dict(id=0,stream_bytes=30,score=1.,automatic_quality_eligible=True),
              dict(id=1,stream_bytes=29,score=.9,automatic_quality_eligible=False)]
        self.assertEqual(choose(rows,30)['selected_id'],0)
        self.assertEqual(choose(rows,30)['raw_id'],1)
        self.assertIsNone(choose(rows,29)['selected_id'])
        self.assertFalse(choose(rows,29)['no_fit'])
        self.assertTrue(choose(rows,28)['no_fit'])

    def test_descriptor_identity_preserves_reset_boundaries(self):
        a=dict(stream_sha256='a',file_bytes=22,index=0,start=0,samples=160,profile=4)
        b=dict(stream_sha256='b',file_bytes=22,index=1,start=160,samples=160,profile=4)
        self.assertNotEqual(descriptors([a,b]),descriptors([b,a]))

    def test_native_reference_handoff_keeps_payload_and_stored_size_separate(self):
        class Array:
            def __init__(self,raw,n):self.raw,self.n=raw,n
            def __len__(self):return self.n
            def astype(self,*args):return self
            def tobytes(self):return self.raw
        class Native:
            def reference(self,*args):
                return dict(pcm=Array(b'\0'*320,160),pwm=Array(b'\x80'*160,160),used=30)
        with scratch() as temporary:
            root=Path(temporary);blob=b'a'*40
            case=dict(id='short-p4',kind='short',profile=4,samples=160,blobs=(blob,),contexts=[],
                segments=[dict(index=0,start=0,samples=160,profile=4,path='unused-source',
                    file_bytes=40,stream_sha256=sha(blob))])
            result=build_case(case,root,Native(),Inputs())
            self.assertEqual(result['stream_bytes'],40)
            self.assertEqual(result['expected_payload_bytes'],30)
            self.assertEqual(result['payload_bytes_by_segment'],[30])
            self.assertEqual(result['offsets'],[FIRST_OFFSET])
            self.assertEqual(Path(result['expected_pwm_path']).stat().st_size,160)
            self.assertEqual(Path(result['expected_pcm16_path']).stat().st_size,320)


if __name__=='__main__':
    unittest.main()
