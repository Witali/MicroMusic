"""Contracts for common starting points; no codec or measured search imports."""
import unittest

from prepare_baselines import strongest


def row(phase,score,size,*,mode='preserve',ordinal=0,profile=4):
    return dict(phase=phase,source_ordinal=ordinal,profile=profile,mode=mode,
        decisions=[dict(percent=100,selected_id=0,cap=1000)],
        report=dict(candidates=[dict(id=0,score=score,stream_bytes=size,automatic_quality_eligible=True)]))


class BaselineContracts(unittest.TestCase):
    def test_strongest_deep_baseline_used_for_both_tiers(self):
        shallow,deep = row('speech-screen',.3,100),row('speech-default',.2,110)
        self.assertIs(strongest([shallow,deep]),deep)
        self.assertIs(strongest([deep,shallow]),deep)

    def test_exact_score_tie_prefers_cost_then_fixed_phase(self):
        shallow,deep = row('speech-screen',.2,100),row('speech-default',.2,110)
        self.assertIs(strongest([deep,shallow]),shallow)
        deep = row('speech-default',.2,100)
        self.assertIs(strongest([shallow,deep]),deep)

    def test_different_level_or_profile_cannot_compete(self):
        seed = row('speech-screen',.3,100)
        for other in (row('speech-default',.2,100,mode='auto-quiet'),
                      row('speech-default',.2,100,profile=6)):
            with self.assertRaises(ValueError):
                strongest([seed,other])

    def test_no_fit_or_ineligible_is_not_a_baseline(self):
        for entry in (row('speech-screen',.2,1001),row('speech-screen',.2,100)):
            if entry['report']['candidates'][0]['stream_bytes']==100:
                entry['report']['candidates'][0]['automatic_quality_eligible']=False
            with self.assertRaises(ValueError):
                strongest([entry])


if __name__=='__main__':
    unittest.main()
