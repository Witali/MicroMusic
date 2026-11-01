"""Pure strongest-seed, context and pilot contracts; no DSP or searches."""
import unittest

from baselines import chain_key,pilot_ids,rank,strongest,successful_row


def candidate(kind,score,size,phase='speech-screen',**kwargs):
    return dict(kind=kind,context=(False,3,4,'preserve'),phase=phase,id=0,
        value=dict(score=score,stream_bytes=size,automatic_quality_eligible=True),**kwargs)


class BaselineContracts(unittest.TestCase):
    def test_stronger_current_cpu_winner_replaces_old_seed(self):
        old=candidate('canonical',.3,100)
        current=candidate('matched-cpu',.2,99,arm='single-path',tier=2,job_id=2)
        self.assertIs(strongest([old,current]),current)
        self.assertIs(strongest([current,old]),current)

    def test_bytes_then_phase_then_canonical_ties(self):
        old=candidate('canonical',.2,100)
        self.assertIs(strongest([old,candidate('matched-cpu',.2,101)]),old)
        default=candidate('matched-cpu',.2,100,'speech-default')
        self.assertIs(strongest([old,default]),default)
        old_default=candidate('canonical',.2,100,'speech-default')
        self.assertIs(strongest([default,old_default]),old_default)

    def test_levels_profiles_and_invalid_candidates_never_mix(self):
        old=candidate('canonical',.3,100)
        wrong=candidate('matched-cpu',.2,100)
        wrong['context']=(False,3,6,'preserve')
        with self.assertRaises(ValueError):strongest([old,wrong])
        wrong=candidate('matched-cpu',.2,100)
        wrong['value']['automatic_quality_eligible']=False
        with self.assertRaises(ValueError):strongest([old,wrong])

    def test_exact_ordered_chain_identity_is_not_combined_size(self):
        a=dict(stream_sha256='first',file_bytes=22,samples=160,profile=4)
        b=dict(stream_sha256='second',file_bytes=22,samples=160,profile=4)
        self.assertNotEqual(chain_key([a,b]),chain_key([b,a]))
        self.assertNotEqual(chain_key([a,b]),chain_key([{**a,'file_bytes':44,'samples':320}]))

    def test_target_admission_requires_complete_physical_output(self):
        report={name:160 for name in ('produced','played','timer_ticks','timer_events')}
        report.update({name:0 for name in ('underruns','decoder_error','observer_errors','observer_exit_code','queued_at_stop')})
        report.update(eof=1,stopped=1,timer_started=1,stack_margin_all_bytes=100)
        row=dict(passed=True,flash_bytes=5000,verification=dict(passed=True),report=report)
        self.assertTrue(successful_row(row,160))
        self.assertFalse(successful_row({**row,'passed':False,'verification':None},160))
        self.assertFalse(successful_row({**row,'report':{**report,'played':159}},160))
        self.assertFalse(successful_row({**row,'report':{**report,'underruns':1}},160))

    def test_metadata_selection_retains_full_multireset_and_profiles(self):
        source=[(False,20,'preserve',32000,1,'tuning'),(False,3,'preserve',63952,1,'tuning'),
            (False,16,'auto-quiet',64000,1,'tuning'),(False,42,'preserve',281632,5,'additional'),
            (True,10,'preserve',10400,1,'non_speech'),(True,65,'preserve',41600,1,'non_speech'),
            (True,7,'preserve',3786111,60,'non_speech')]
        bases=[]
        for ns,ordinal,mode,n,resets,split in source:
            for profile in (4,6):
                bases.append(dict(id=len(bases),nonspeech=ns,source_ordinal=ordinal,mode=mode,samples=n,
                    segments=[{}]*resets,split=split,profile=profile))
        chosen=[b for b in bases if b['id'] in pilot_ids(bases)]
        self.assertEqual(len(chosen),12)
        self.assertEqual(sum(len(b['segments']) for b in chosen),20)
        self.assertEqual({b['profile'] for b in chosen},{4,6})
        self.assertFalse(any(b['nonspeech'] and b['source_ordinal']==7 for b in chosen))


if __name__=='__main__':unittest.main()
