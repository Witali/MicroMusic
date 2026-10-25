"""Keep the previously heard stimulus out of independent corpus summaries."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from summarize_multiseed import groups


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


if __name__=='__main__':unittest.main()
