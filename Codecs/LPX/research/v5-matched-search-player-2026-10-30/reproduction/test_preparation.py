"""Pure strongest-baseline and complete inventory admission contracts."""
import unittest

from prepare_player import canonical100,decision_from_rows,manifest_map,strongest


class PreparationContracts(unittest.TestCase):
    def source(self,phase,score,size=100,mode='auto-quiet'):
        value = dict(id=0,score=score,stream_bytes=size,automatic_quality_eligible=True)
        decision = dict(percent=100,**decision_from_rows([value],200))
        return dict(phase=phase,source_ordinal=0,profile=4,mode=mode,
                    decisions=[decision],report=dict(candidates=[value]))

    def test_same_context_uses_stronger_whole_source(self):
        screen,default = self.source('speech-screen',1),self.source('speech-default',2)
        self.assertIs(strongest([screen,default]),screen)

    def test_tied_whole_sources_have_fixed_priority(self):
        screen,default = self.source('speech-screen',1),self.source('speech-default',1)
        self.assertIs(strongest([screen,default]),default)

    def test_different_levels_never_compete(self):
        with self.assertRaises(ValueError):
            strongest([self.source('speech-screen',1),self.source('speech-default',0,mode='preserve')])

    def test_nonbest_recorded_canonical_choice_fails(self):
        row = self.source('speech-screen',2)
        row['report']['candidates'].append(dict(id=1,score=1,stream_bytes=100,automatic_quality_eligible=True))
        with self.assertRaises(ValueError):canonical100(row)

    def inventory(self,parts,baseline=(b'a',b'b')):
        context = dict(job_id=0,baseline_id=0,phase='speech-screen',source_ordinal=0,profile=4,
            mode='auto-quiet',arm='trajectory',tier_label='2',percent=100,
            rollback=[dict(blob=blob,file_bytes=len(blob)) for blob in baseline])
        return dict(profile=4,samples=1,stream_bytes=sum(map(len,parts)),parts=parts,contexts=[context])

    @staticmethod
    def chain(item,profile):
        return item.get('parts',tuple(part['blob'] for part in item.get('segments',())))

    def test_order_and_exact_rollback_are_preserved(self):
        left = self.inventory((b'c',b'd'))
        right = self.inventory((b'd',b'c'),baseline=(b'b',b'a'))
        value = manifest_map([left,right],self.chain)
        self.assertEqual(len(value),2)
        self.assertEqual(value[(b'd',b'c')][0][-1],(b'b',b'a'))

    def test_duplicate_inventory_or_context_fails(self):
        item = self.inventory((b'c',b'd'))
        with self.assertRaises(ValueError):manifest_map([item,item],self.chain)
        item['contexts'] *= 2
        with self.assertRaises(ValueError):manifest_map([item],self.chain)


if __name__=='__main__':unittest.main()
