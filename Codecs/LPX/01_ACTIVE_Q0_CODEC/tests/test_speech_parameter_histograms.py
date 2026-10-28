import json
import unittest

import speech_compact as compact
from speech_parameter_histograms import parameter_histograms
from test_speech_v4 import fixture


class SpeechParameterHistogramTests(unittest.TestCase):
    def test_exact_field_deltas_repeats_and_marker_arithmetic(self):
        values=list(compact.unpack(compact.repack(fixture(6,801))[0]))
        values[3]=[(2,20,4),(2,20,4),(3,22,6),(3,22,6),(1,21,0),(1,21,0)]
        blob=compact.pack(*values[:7],extras=values[7])[0]
        result=parameter_histograms([blob]);stored=result['groups']['stored']
        self.assertEqual(stored['packets'],6);self.assertEqual(stored['transitions'],5)
        self.assertEqual(stored['tuple_repeats'],3)
        self.assertEqual(stored['fields']['scale']['delta'],{'-2':1,'0':3,'1':1})
        self.assertEqual(stored['fields']['lag']['delta'],{'-1':1,'0':3,'2':1})
        self.assertEqual(stored['fields']['gain_code']['delta'],{'-3':1,'0':3,'1':1})
        self.assertEqual(stored['current_fixed_parameter_bits'],90)
        self.assertEqual(stored['hypothetical_tuple_repeat_bits'],50)
        self.assertEqual(stored['hypothetical_independent_field_repeat_bits'],60)
        self.assertFalse(result['format_implemented'])

    def test_partial_tail_and_stream_boundaries_are_separate(self):
        values=list(compact.unpack(compact.repack(fixture(4,1))[0]))
        values[3]=[(31,145,14),(0,18,0)]
        blob=compact.pack(*values[:7],extras=values[7])[0]
        result=parameter_histograms([blob,blob]);stored=result['groups']['stored'];audible=result['groups']['audible']
        self.assertEqual(result['stored_unplayed_packets'],2)
        self.assertEqual(stored['first_packets'],2);self.assertEqual(stored['transitions'],2)
        self.assertEqual(stored['fields']['lag']['delta'],{'-127':2})
        self.assertEqual(audible['packets'],2);self.assertEqual(audible['transitions'],0)
        self.assertEqual(audible['current_fixed_parameter_bits'],30)
        self.assertEqual(audible['hypothetical_tuple_repeat_bits'],30)
        text=json.dumps(result)
        self.assertNotIn('sha256',text);self.assertNotIn('path',text)

    def test_empty_and_invalid_inputs(self):
        result=parameter_histograms([])
        self.assertEqual(result['streams'],0)
        self.assertEqual(result['groups']['stored']['current_fixed_parameter_bits'],0)
        with self.assertRaises(ValueError):parameter_histograms([b'not-v5'])


if __name__=='__main__':unittest.main()
