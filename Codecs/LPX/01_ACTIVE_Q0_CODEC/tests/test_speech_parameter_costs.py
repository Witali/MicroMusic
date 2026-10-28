"""Actual v5 cursor and exact hypothetical whole-byte arithmetic, no new format."""
import struct
import unittest

import speech_compact as compact
from lpx4 import BitWriter
from speech_parameter_costs import METHODS,chain_cost,inspect_stream,parameter_bits,stream_cost
from speech_parameter_histograms import FIELDS,parameter_codes
from test_speech_v4 import fixture


def zero_amplitude_marker(profile=6,n=1):
    source=compact.repack(fixture(profile,n))[0];v=compact.unpack(source)
    header=bytearray(source[:20]);header[5]|=128
    writer=BitWriter();old=None
    for fi,vec in enumerate(v[2]):
        compact.put_spectrum(writer,vec,old,5 if profile==4 else 6);old=vec
        for half in range(2):
            scale,lag,gain=v[3][fi*2+half];writer.put(scale,5);writer.put(lag-18,7);writer.put(gain//2,3)
            for chunk in range(4):
                a,b=v[4][fi*16+half*8+chunk*2:fi*16+half*8+chunk*2+2]
                if profile==4:
                    for pos,amp in (a,b):
                        writer.put(int(list(compact.v4.POSITIONS4).index(pos)),4);writer.put(int(amp>0),1)
                else:
                    pair=a[0]+20*b[0];writer.put(pair&255,8);writer.put(pair>>8,1)
                    writer.put(a[1]&15,4);writer.put(b[1]&15,4)
                marker=fi==0 and half==0 and chunk==0;writer.put(int(marker),1)
                if marker:writer.put(5,6);writer.put(0,4)
    bits=writer.total;writer.aligned();payload=writer.get()
    return bytes(header)+struct.pack('<H',len(payload))+payload,bits


def independent_parameter_writer(params,method):
    coded=parameter_codes(params);writer=BitWriter()
    for value,(_,width) in zip(coded[0],FIELDS):writer.put(value,width)
    for before,after in zip(coded,coded[1:]):
        for i,(_,width) in enumerate(FIELDS):
            value=after[i]
            if not method.mask&(1<<i):writer.put(value,width)
            elif method.kind=='repeat':
                same=value==before[i];writer.put(0 if same else 1,1)
                if not same:writer.put(value,width)
            else:
                delta=value-before[i];z=delta*2 if delta>=0 else -2*delta-1
                if z>>method.k>=8:writer.put(0,8);writer.put(value,width)
                else:compact.putrice(writer,z,method.k,width+1)
    return writer.total


class ParameterCostTests(unittest.TestCase):
    def test_actual_payload_and_forced_empty_extras_partial_tails(self):
        for profile in (4,6):
            for n in (1,319,320,321,641,1280):
                values=compact.unpack(compact.repack(fixture(profile,n))[0])
                extras=[(-1,0)]*(len(values[2])*8)
                for force in (False,True):
                    blob,meta=compact.pack(*values[:7],extras=extras,force_extras=force)
                    info=inspect_stream(blob)
                    self.assertEqual(info['current_payload_bits'],meta['payload_bits'])
                    self.assertEqual(info['current_padding_bits'],(-meta['payload_bits'])%8)
                    self.assertEqual(info['stored_tuples'],len(values[2])*2)
                    self.assertEqual(info['source_extra_marker_bits'],len(extras) if force else 0)
                    self.assertEqual(info['source_extra_value_bits'],0)
                    for method in METHODS:
                        cost=stream_cost(blob,method)
                        self.assertEqual(cost['untouched_payload_bits'],info['current_payload_bits']-15*len(values[3]))
                        self.assertEqual(cost['proposed_file_bytes'],23+(cost['proposed_payload_bits']+7)//8)
                        self.assertEqual(cost['additional_selector_bytes'],1)
                        self.assertEqual(cost['unplayed_stored_tuples'],len(values[3])-(n+159)//160)

    def test_legal_zero_amplitude_marker_is_not_canonicalized(self):
        for profile in (4,6):
            source,bits=zero_amplitude_marker(profile)
            info=inspect_stream(source);values=compact.unpack(source)
            self.assertEqual(info['current_payload_bits'],bits)
            self.assertEqual(info['source_extra_marker_bits'],8)
            self.assertEqual(info['source_extra_value_bits'],10)
            canonical,meta=compact.pack(*values[:7],extras=values[7],force_extras=True)
            self.assertEqual(bits-meta['payload_bits'],10)
            for method in METHODS:
                actual=stream_cost(source,method);normalized=stream_cost(canonical,method)
                self.assertEqual(actual['proposed_payload_bits']-normalized['proposed_payload_bits'],10)

    def test_all_predeclared_methods_match_existing_writer_and_absolute_escape(self):
        params=[(0,18,0),(31,145,14),(30,144,12),(0,18,0),(0,18,0),(1,19,2)]
        self.assertEqual(len(METHODS),13)
        self.assertEqual({m.mask for m in METHODS if m.kind=='repeat'},set(range(1,8)))
        for method in METHODS:
            result=parameter_bits(params,method)
            self.assertEqual(result['bits'],independent_parameter_writer(params,method))
            self.assertEqual(result['initial_absolute_bits'],15)
            self.assertEqual(result['bits'],sum(f['initial_absolute_bits']+f['transition_bits'] for f in result['fields'].values()))
        normal=next(m for m in METHODS if m.kind=='rice' and m.mask==7 and m.k==0)
        self.assertGreater(parameter_bits(params,normal)['fields']['lag']['absolute_escapes'],0)

    def test_unused_lag_and_history_are_retained(self):
        repeat_lag=next(m for m in METHODS if m.kind=='repeat' and m.mask==2)
        same=[(7,18,0),(7,18,0)];different=[(7,18,0),(7,145,0)]
        self.assertEqual(parameter_bits(different,repeat_lag)['bits']-parameter_bits(same,repeat_lag)['bits'],7)
        for method in METHODS:
            self.assertEqual(parameter_bits(same[:1],method)['bits'],15)
        self.assertEqual(parameter_codes(different),[(7,0,0),(7,127,0)])

    def test_each_segment_header_initial_tuple_and_padding_are_charged(self):
        blobs=[compact.repack(fixture(4,1),force_extras=True)[0],compact.repack(fixture(4,321),force_extras=True)[0]]
        independent_padding_matters=False
        for method in METHODS:
            result=chain_cost(blobs,method);parts=result['segment_costs']
            self.assertEqual(result['proposed_file_bytes'],sum(p['proposed_file_bytes'] for p in parts))
            self.assertEqual(sum(p['additional_selector_bytes'] for p in parts),2)
            self.assertEqual(sum(p['parameter_detail']['initial_absolute_bits'] for p in parts),30)
            falsely_joined=46+(sum(p['proposed_payload_bits'] for p in parts)+7)//8
            independent_padding_matters|=falsely_joined!=result['proposed_file_bytes']
        self.assertTrue(independent_padding_matters)

    def test_illegal_inputs_fail_and_source_parameters_are_not_changed(self):
        params=[(4,55,0),(5,145,14)];before=params.copy()
        for method in METHODS:parameter_bits(params,method)
        self.assertEqual(params,before)
        for bad in ([(0,17,0)],[(0,146,0)],[(32,18,0)],[(0,18,3)],[(0.,18,0)],[]):
            with self.assertRaises(ValueError):parameter_bits(bad,METHODS[0])
        with self.assertRaises(ValueError):chain_cost([],METHODS[0])
        with self.assertRaises(ValueError):chain_cost(b'not-a-chain',METHODS[0])
        with self.assertRaises(ValueError):inspect_stream(b'bad')
        a=compact.repack(fixture(4,1))[0];b=compact.repack(fixture(6,1))[0]
        with self.assertRaises(ValueError):stream_cost(b,METHODS[0],inspect_stream(a))
        with self.assertRaises(ValueError):chain_cost([a],METHODS[0],[])


if __name__=='__main__':unittest.main()
