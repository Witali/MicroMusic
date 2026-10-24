"""Fixed records, gain-window expansion, headers and grouped fit mutations."""
import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'ATtiny13A/Sound/codec'))
import q4_product233 as codec
spec=importlib.util.spec_from_file_location('product233_contracts',ROOT/'tools/fit-q4-product233.py')
fit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=fit;spec.loader.exec_module(fit)


class Product233Tests(unittest.TestCase):
    def books(self):
        root=np.zeros((16,4),np.int16);middle=np.zeros((16,3),np.int16);tail=middle.copy()
        root[0]=[-15,15,7,7];middle[0]=15;tail[0]=-15
        root[1:,:2]=np.arange(30).reshape(15,2)%31-15
        root[1:,2]=np.arange(15)%8;root[1:,3]=np.arange(15)%8
        return root,middle,tail

    def test_exact_16_bit_records_preserve_signs_selectors_and_little_endian_order(self):
        books=self.books();data=codec.pack_tables(*books)
        self.assertEqual(len(data),96)
        self.assertEqual(data[:2],b'\xe1\xff');self.assertEqual(data[32:34],b'\xff\x7f')
        self.assertEqual(data[64:66],b'\x21\x04')
        for expected,actual in zip(books,codec.unpack_tables(data)):np.testing.assert_array_equal(expected,actual)
        for invalid in (bytes(96),data[:-1],data[:33]+bytes([data[33]|128])+data[34:]):
            with self.assertRaises(ValueError):codec.unpack_tables(invalid)

    def test_all_frame_fields_round_trip_with_only_pitch_fraction_duration_extensions(self):
        fields=[(p,g,d,[i,(i+1)%16,(i+7)%16],h)
            for p in (0,1,63,64,126) for g in range(16) for d in (64,128,192,256)
            for i in range(16) for h in (0,1) if p or not h]
        values=tuple(np.asarray(a,np.int16) for a in zip(*fields))
        data=codec.pack_frames(*values)
        for expected,actual in zip(values,codec.unpack_frames(data)):np.testing.assert_array_equal(expected,actual)
        self.assertEqual(len(codec.pack_frames(np.array([40]),np.array([15]),np.array([64]),
            np.array([[15,15,15]]),np.array([0]))),3)
        for invalid in (b'',b'\xff',b'\xc4\x01\x00\x00',b'\xc0',b'\x40\x00'):
            with self.assertRaises(ValueError):codec.unpack_frames(invalid)

    def test_gain_windows_expand_exactly_and_reject_the_one_out_of_range_code(self):
        root,mid,tail=self.books();i=np.array([[0,0,0]],np.int16)
        values=(np.array([40]),np.array([14]),np.array([64]),i,np.array([0]))
        p,g,d,k,m,h=codec.expand(*values,root,mid,tail)
        self.assertEqual((int(g[0]),int(m[0])),(30,7))
        np.testing.assert_array_equal(k[0],[-15,15,15,15,15,-15,-15,-15])
        bad=list(values);bad[1]=np.array([15])
        with self.assertRaises(ValueError):codec.expand(*bad,root,mid,tail)

    def test_index_changes_preserve_gain_when_the_new_window_covers_it(self):
        root,mid,tail=self.books();root[:]=0;root[1,3]=2
        s=fit.State(np.array([40]),np.array([10]),np.array([128]),np.zeros((1,3),np.int16),
            np.array([0]),root,mid,tail,np.zeros((8,16),np.int16))
        before=s.fields();changed=fit.apply(s,('index',0,0,1))
        self.assertEqual(s.fields(),before);self.assertEqual(int(changed.local_gains[0]),6)
        self.assertEqual(int(fit.expand(changed).gains_q1[0]),10)
        for action in (('coefficient',0,1,0,1),('gain',0,0,-1),('pitch',0,0,1),('wave',0,0,1)):
            candidate=fit.apply(s,action);self.assertIsNotNone(candidate);fit.expand(candidate)
            self.assertEqual(s.fields(),before)

    def test_phase_flags_use_reserved_record_bits_without_growing_the_tables(self):
        books=self.books();attack=(np.arange(16)%2).astype(np.int16);hold=((np.arange(16)//2)%2).astype(np.int16)
        payload=codec.pack_tables(*books,attack,hold);self.assertEqual(len(payload),96)
        for expected,actual in zip((*books,attack,hold),codec.unpack_tables(payload,phase_flags=True)):
            np.testing.assert_array_equal(expected,actual)
        with self.assertRaises(ValueError):codec.unpack_tables(payload)
        with self.assertRaises(ValueError):codec.pack_tables(*books,np.full(16,2),hold)

    def test_zero_phase_flags_preserve_legacy_pcm_and_hold_avoids_short_frame_starvation(self):
        root=np.zeros((16,4),np.int16);book=np.zeros((16,3),np.int16)
        s=fit.State(np.full(8,90,np.int16),np.full(8,2,np.int16),np.full(8,64,np.int16),
            np.zeros((8,3),np.int16),np.zeros(8,np.int16),root,book,book.copy(),np.zeros((8,16),np.int16))
        s.waves_q1[0,0]=4
        actual,counts=fit.render(s,4,True);old,old_counts=fit.fit.render(fit.expand(s),4,True)
        np.testing.assert_array_equal(actual,old);np.testing.assert_array_equal(counts,old_counts)
        np.testing.assert_array_equal(actual,np.full(len(actual),128,np.uint8))
        s.hold_flags[0]=1;continuous,cc=fit.render(s,4,True)
        self.assertTrue(np.any(continuous!=128));self.assertFalse(np.any(cc));self.assertEqual(int(continuous[0]),128)
        s.hold_flags[0]=0;s.attack_flags[0]=1;immediate,ic=fit.render(s,4,True)
        self.assertNotEqual(int(immediate[0]),128);self.assertFalse(np.any(ic))

    def test_physical_compaction_preserves_pcm_and_restricted_fit_cannot_restore_removed_forms(self):
        spec=importlib.util.spec_from_file_location('product_form_pruner_contracts',ROOT/'tools/prune-q4-product-forms.py')
        prune=importlib.util.module_from_spec(spec);sys.modules[spec.name]=prune;spec.loader.exec_module(prune)
        root=np.zeros((16,4),np.int16);root[:,2]=7;root[1,2]=3
        book=np.zeros((16,3),np.int16)
        s=fit.State(np.full(4,40,np.int16),np.full(4,2,np.int16),np.full(4,128,np.int16),
            np.array([[0,0,0],[1,0,0],[0,0,0],[1,0,0]],np.int16),np.zeros(4,np.int16),
            root,book,book.copy(),np.zeros((8,16),np.int16))
        s.waves_q1[7,:2]=[4,-2];s.waves_q1[3,:2]=[2,-4]
        before=s.fields();reduced=prune.compact(s,4,True)
        self.assertEqual(s.fields(),before);np.testing.assert_array_equal(prune.active(reduced),[0,1])
        self.assertFalse(np.any(reduced.waves_q1[2:]));self.assertTrue(np.all(reduced.root[:,2]<2))
        for a,b in zip(fit.render(s,4,True),fit.render(reduced,4,True)):np.testing.assert_array_equal(a,b)
        model=dict(schema=codec.PHASE_SCHEMA,maximum_forms=2,**reduced.fields())
        fit.from_model(model)
        for action in fit.actions(reduced,True,2):
            if action[0]=='mode':self.assertLess(action[3],2)
            if action[0]=='wave':self.assertLess(action[1],2)
        for maximum in (0,1,9):
            with self.assertRaises(ValueError):fit.from_model(dict(model,maximum_forms=maximum))


if __name__=='__main__':unittest.main()
