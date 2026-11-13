"""Independent stdlib checks for the frozen, unadmitted Rice0 experiment."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from speech_v9_rice0_experiment import Bits,pulse_pair,repack
from speech_v9 import repack as production_repack


def _rice(writer,value,k,width):
    quotient=value>>k
    if quotient>=8:writer.put(0,8);writer.put(value,width)
    else:writer.put(0,quotient);writer.put(1,1);writer.put(value&((1<<k)-1),k)


def _spectrum(writer,vector,old,bits,delta_k0,force_delta):
    if vector==old and not force_delta:writer.put(0,1);return
    choices=[]
    for delta in (False,True):
        if delta and old is None:continue
        if force_delta and old is not None and not delta:continue
        values=([2*(a-b) if a>=b else -2*(a-b)-1 for a,b in zip(vector,old)] if delta else
                [vector[0]]+[b-a-1 for a,b in zip(vector,vector[1:])])
        k=(0 if delta_k0 else bits-5) if delta else bits-4
        trial=Bits()
        for value in values:_rice(trial,value,k,bits+int(delta))
        choices.append((trial.at,delta,values,k))
    _,delta,values,k=min(choices,key=lambda choice:(choice[0],choice[1]))
    writer.put(1,1);writer.put(int(delta),1)
    for value in values:_rice(writer,value,k,bits+int(delta))


def _fixture(profile,n,style,extras,*,delta_k0=False,force_delta=False):
    if profile not in (4,6,15) or type(n) is not int or not 1<=n<=64000:
        raise ValueError('Invalid fixture geometry')
    if extras and profile==15:raise ValueError('Sparse80 has no extras markers')
    if style not in ('small','constant','escape','growth','negative'):
        raise ValueError('Unknown fixture style')
    flags=profile|(128 if extras else 0)|(64 if delta_k0 and profile!=4 else 0)
    writer=Bits();old=None
    for fi in range((n+319)//320):
        if profile==4:vector=[1+3*i+(fi%2 if i==0 and style=='small' else 0) for i in range(10)]
        elif style=='escape':vector=list(range(54,64)) if fi%2 else list(range(10))
        elif style=='growth':vector=[3+6*i+(4 if fi%2 and i<2 else 0) for i in range(10)]
        elif style=='negative':vector=[3+6*i+(4 if fi==0 and i==0 else 0) for i in range(10)]
        else:vector=[3+6*i+(fi%2 if i==0 and style=='small' else 0) for i in range(10)]
        _spectrum(writer,vector,old,5 if profile==4 else 6,delta_k0,force_delta);old=vector
        def metadata(half):
            gain=(fi+half)%8;writer.put((fi+half)%32,5);writer.put(gain,3)
            if gain:writer.put((fi*17+half*11)%128,7)
        if profile==15:
            metadata(0)
            for group in range(4):
                if fi*320+group*80<n:writer.put((fi*4+group)%128,7)
        else:
            for half in range(2):
                offset=fi*320+half*160
                if offset>=n:continue
                metadata(half)
                for sub in range(4):
                    if offset+sub*40>=n:continue
                    index=fi*8+half*4+sub
                    if profile==4:writer.put((index*79)%1024,10)
                    else:writer.put(pulse_pair(index%20,(index//20)%20),9);writer.put(index%256,8)
                    if extras:
                        present=index%3!=0;writer.put(int(present),1)
                        if present:writer.put(index%40,6);writer.put(index%16,4)
    return struct.pack('<2sBHHHHH',b'L9',flags,8000,n,8192,11469,len(writer.output))+writer.output


def fixture(profile,n,style='small',extras=False):
    """Return deterministic canonical OLD-v9 bytes for native receiver matrices.

    Profiles4/6/15,1..64000samples; small/constant/escape/growth/negative LSF
    styles. P4/P6 may include extras. P6 at16000samples covers all400 position
    pairs. Metadata includes zero/nonzero gain, wide lags and signed pulses.
    """
    return bytes(_fixture(profile,n,style,extras))


class Rice0TranscodingTests(unittest.TestCase):
    def test_default_and_legacy_roundtrips_stay_exact(self):
        for profile in (4,6,15):
            for extras in ((False,True) if profile!=15 else (False,)):
                for n in list(range(1,41))+[79,80,81,159,160,161,319,320,321,641,16000,64000]:
                    original=fixture(profile,n,extras=extras)
                    default,stats=repack(original)
                    self.assertEqual(default,original);self.assertNotIn('rice0_optimization',stats)
                    legacy_version=8 if profile==15 else 5
                    legacy,_=repack(original,legacy_version)
                    self.assertEqual(legacy,production_repack(original,legacy_version)[0])
                    self.assertEqual(repack(legacy)[0],original)
                    self.assertEqual(repack(legacy)[0],production_repack(legacy)[0])
                    selected,selected_stats=repack(original,optimize_rice0=True)
                    self.assertLessEqual(len(selected),len(original))
                    self.assertEqual(repack(selected)[0],selected)
                    self.assertEqual(repack(selected,optimize_rice0=True)[0],selected)
                    self.assertEqual(repack(selected,legacy_version)[0],legacy)
                    self.assertEqual(repack(legacy,optimize_rice0=True)[0],selected)
                    optimization=selected_stats['rice0_optimization']
                    self.assertEqual(optimization['saved_bytes'],len(original)-len(selected))
                    self.assertEqual(8*optimization['saved_bytes'],optimization['saved_payload_bits']+optimization['saved_padding_bits'])

    def test_k0_selected_only_for_strict_file_savings(self):
        for profile in (6,15):
            original=fixture(profile,64000)
            selected,stats=repack(original,optimize_rice0=True)
            self.assertEqual(selected[2],original[2]|64)
            self.assertLess(len(selected),len(original))
            self.assertEqual(stats['rice0_optimization']['decision'],'k0')
        for style,expected in (('growth','fallback-growth'),('constant','fallback-byte-tie')):
            original=fixture(6,64000,style)
            selected,stats=repack(original,optimize_rice0=True)
            self.assertEqual(selected,original);self.assertEqual(stats['rice0_optimization']['decision'],expected)
        found=False
        for n in range(321,641,40):
            original=fixture(6,n,'negative');selected,stats=repack(original,optimize_rice0=True)
            result=stats['rice0_optimization']
            if result['candidate_payload_bits']<result['baseline_payload_bits'] and result['candidate_file_bytes']==len(original):
                self.assertEqual(selected,original);found=True;break
        self.assertTrue(found,'Byte padding can hide genuine bit savings')

    def test_noncanonical_original_is_retained_exactly(self):
        original=bytes(_fixture(6,641,'constant',False,force_delta=True))
        self.assertEqual(repack(original)[0],original)
        selected,stats=repack(original,optimize_rice0=True)
        self.assertEqual(selected,original)
        self.assertEqual(stats['rice0_optimization']['decision'],'fallback-noncanonical-exact-roundtrip')

    def test_zero_deltas_signed_escapes_and_forced_new_syntax(self):
        for profile in (6,15):
            for style in ('small','constant','escape','growth','negative'):
                for extras in ((False,True) if profile==6 else (False,)):
                    forced=bytes(_fixture(profile,1280,style,extras,delta_k0=True,force_delta=True))
                    self.assertTrue(forced[2]&64)
                    self.assertEqual(repack(forced)[0],forced)
                    legacy_version=8 if profile==15 else 5
                    expected=repack(fixture(profile,1280,style,extras),legacy_version)[0]
                    actual=repack(forced,legacy_version)[0]
                    self.assertEqual(actual,expected);self.assertFalse(actual[5]&64)

    def test_redundant_p4_input_flag_is_accepted_but_never_added(self):
        for extras in (False,True):
            original=fixture(4,1280,extras=extras)
            self.assertEqual(repack(original,optimize_rice0=True)[0],original)
            redundant=bytearray(original);redundant[2]|=64
            self.assertEqual(repack(bytes(redundant))[0],redundant)
            self.assertEqual(repack(bytes(redundant),optimize_rice0=True)[0],redundant)
            legacy=repack(bytes(redundant),5)[0]
            self.assertFalse(legacy[5]&64);self.assertEqual(legacy,repack(original,5)[0])

    def test_invalid_headers_padding_and_options_fail_closed(self):
        original=fixture(6,321)
        for flag in (0,7,14,31,127,143,255):
            damaged=bytearray(original);damaged[2]=flag
            with self.assertRaises(ValueError):repack(damaged)
        for version in (5,8):
            source=fixture(15 if version==8 else 6,641)
            legacy=bytearray(repack(source,version)[0]);legacy[5]|=64
            with self.assertRaises(ValueError):repack(legacy)
        selected=repack(fixture(6,1280),optimize_rice0=True)[0]
        for damaged in (selected[:-1],selected+b'\0'):
            with self.assertRaises(ValueError):repack(damaged)
        for n in range(321,641):
            blob=fixture(15,n);_,stats=repack(blob)
            if stats['payload_bits']%8:
                damaged=bytearray(blob);damaged[-1]|=128
                with self.assertRaises(ValueError):repack(damaged,optimize_rice0=True)
                break
        for value in (1,None,'yes'):
            with self.assertRaises(ValueError):repack(original,optimize_rice0=value)
        for version in (5,8):
            with self.assertRaises(ValueError):repack(original,version,optimize_rice0=True)

    def test_explicit_cli_switch_matches_api(self):
        temporary_root=ROOT.parents[2]/'build/speech-v9-rice0-tests';temporary_root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as directory:
            folder=Path(directory);source=folder/'source.lpx';source.write_bytes(fixture(6,1280))
            output=folder/'selected.lpx'
            result=subprocess.run([sys.executable,str(ROOT/'tools/speech_v9_rice0_experiment.py'),str(source),str(output),'--optimize-rice0'],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            self.assertEqual(output.read_bytes(),repack(source.read_bytes(),optimize_rice0=True)[0])
            self.assertTrue(folder.resolve().is_relative_to(temporary_root.resolve()))


if __name__=='__main__':unittest.main()
