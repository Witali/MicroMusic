"""Keep the previously heard stimulus out of independent corpus summaries."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from summarize_multiseed import groups,paired


class MultiseedSummaryTests(unittest.TestCase):
    def test_stimulus_exclusion_does_not_drop_other_members(self):
        cases=[{'id':'ru_pushkin_a4','group':'clean','split':'tuning'},
               {'id':'unheard','group':'clean','split':'validation'},
               {'id':'piano','group':'acoustic_music','split':'control'}]
        result=groups(cases)
        self.assertEqual([c['id'] for c in result['all_except_stimulus']],['unheard','piano'])
        self.assertEqual([c['id'] for c in result['clean_except_stimulus']],['unheard'])
        self.assertEqual([c['id'] for c in result['tuning']],['ru_pushkin_a4'])
        self.assertEqual([c['id'] for c in result['validation']],['unheard'])

    def test_quality_byte_and_peak_gains_remain_separate(self):
        def point(error,ser,peak,bytes,changed):
            return {'status':'ok','file_bytes':bytes,'audio_packet_bytes':bytes-20,
                'metrics':{'aligned_pcm16':{'reference_energy':10000,'error_energy':error,'samples':100,
                    'ser_db':ser,'stoi':.8,'max_abs_error_pcm16':peak}},
                'changed':changed,'spectrum_changed':changed,'raw_best_rejected_by_stoi':False}
        a={'id':'a','rates':[{'ceiling_bps':12000,'baseline':point(10000,0,20,100,False),
                            'enhanced':point(5000,3.0103,25,110,True)}]}
        b={'id':'b','rates':[{'ceiling_bps':12000,'baseline':point(10000,0,20,100,False),
                            'enhanced':point(10000,0,20,90,True)}]}
        result=paired([a,b],12000,'enhanced','aligned_pcm16')
        self.assertEqual(result['error_improved'],['a']);self.assertEqual(result['error_equal'],['b'])
        self.assertEqual(result['byte_improved'],['b']);self.assertEqual(result['byte_larger'],['a'])
        self.assertEqual(result['peak_worse'],['a']);self.assertEqual(result['ser_gain_at_least_0_5db'],['a'])
        self.assertAlmostEqual(result['ser_gain_median_db'],1.50515)


if __name__=='__main__':unittest.main()
