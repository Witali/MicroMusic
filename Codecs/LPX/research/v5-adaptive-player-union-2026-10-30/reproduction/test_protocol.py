"""Synthetic exact-union/admission contracts; no encoding or player builds."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path[:0]=[str(HERE),str(ROOT/'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools')]
import speech_compact as compact
from prepare_union import Union, FLASH_BYTES, sha, audit_gate, same
from measure_union import context


def blob(pre=8192,n=1,extras=False):
    frames=(n+319)//320
    spectra=[[2,5,8,11,14,17,20,23,26,29]]*frames
    return compact.pack(n,4,spectra,[(12,40,12)]*(2*frames),[(0,8)]*(16*frames),
        pre=pre,extras=[(0,2) if extras else (-1,0)]*(8*frames))[0]


class UnionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.folder=Path(self.temporary.name)
    def tearDown(self):self.temporary.cleanup()
    def entry(self,name,streams,role='control',eligible=True):
        parts=[];start=0
        for index,data in enumerate(streams):
            path=self.folder/(name+'-%d.l4hy'%index);path.write_bytes(data)
            n,profile=compact.unpack(data)[:2]
            parts.append(dict(path=str(path),stream_sha256=sha(data),file_bytes=len(data),index=index,start=start,samples=n,profile=profile));start+=n
        return dict(role=role,samples=start,segments=parts,stream_bytes=sum(map(len,streams)),
            pcm16_sha256=sha(b'fixture PCM'+b''.join(streams)),pwm_sha256=sha(b'fixture PWM'+b''.join(streams)),automatic_quality_eligible=eligible)
    def record(self,control,candidate,raw=None,phase='speech-screen'):
        return dict(chains=[control,candidate,raw],profile=4,speech=True,source_ordinal=1,mode='preserve',level=dict(gain=1),
            targeted_not_independent_heldout=False,phase=phase,budgets=[dict(percent=100,cap=999,selected='concat-selected'),
            dict(percent=95,cap=999,selected='concat-selected'),dict(percent=90,cap=999,selected='control')])
    def test_caps_and_paired_phases_share_exact_images(self):
        control=self.entry('old',[blob()]);candidate=self.entry('new',[blob(pre=0)],'concat-selected')
        raw=dict(candidate,role='concat-raw',automatic_quality_eligible=False,segments=[dict(candidate['segments'][0],path=str(self.folder/'missing'))])
        union=Union(compact.unpack)
        self.assertEqual(union.add_record(self.record(control,candidate,raw)),dict(observed=3,changed=2,unchanged=1,no_automatic_selection=0))
        union.add_record(self.record(control,candidate,raw,phase='speech-default'))
        self.assertEqual(len(union.registry),2)
        self.assertEqual(len(union.comparisons),1)
        self.assertEqual(len(next(iter(union.comparisons.values()))['selections']),4)
    def test_ineligible_raw_or_oversized_selected_chain_is_rejected(self):
        control=self.entry('old',[blob()]);candidate=self.entry('new',[blob(pre=0)],'concat-selected')
        record=self.record(control,candidate)
        record['chains'][1]['automatic_quality_eligible']=False
        with self.assertRaises(ValueError):Union(compact.unpack).add_record(record)
        record['chains'][1]['automatic_quality_eligible']=True;record['budgets'][0]['cap']=1
        with self.assertRaises(ValueError):Union(compact.unpack).add_record(record)
    def test_order_and_offsets_are_actual_chain_identity(self):
        first,second=blob(),blob(pre=0)
        ab=self.entry('ab',[first,second]);ba=self.entry('ba',[second,first])
        union=Union(compact.unpack)
        self.assertNotEqual(union.chain(ab,4),union.chain(ba,4))
        ab['segments'][1]['start']=0
        with self.assertRaises(ValueError):union.chain(ab,4)
    def test_data_alone_no_fit_does_not_truncate_chain(self):
        data=blob(n=64000,extras=True);count=FLASH_BYTES//len(data)+1
        entry=self.entry('large',[data]*count)
        streams=Union(compact.unpack).chain(entry,4)
        self.assertGreater(sum(map(len,streams)),FLASH_BYTES)
        self.assertEqual(len(streams),count)
        self.assertEqual(entry['samples'],count*64000)
    def test_pending_or_partial_gate_cannot_launch_images(self):
        with self.assertRaises(ValueError):audit_gate(None,None,None,None,dict(missing_records=1,all_six_workers_complete=False))
        path=self.folder/'estimate.json';path.write_text(json.dumps(dict(schema='lpx-v5-adaptive-player-union-estimate-private-v1',image_launch_allowed=False)))
        with self.assertRaises(AssertionError):context(SimpleNamespace(handoff=path))
    def test_metric_pin_comparison_rejects_nonfinite_or_changed_values(self):
        self.assertTrue(same(.5,.5));self.assertTrue(same(None,None))
        self.assertFalse(same(float('nan'),.5));self.assertFalse(same(.50001,.5))


if __name__=='__main__':unittest.main()
