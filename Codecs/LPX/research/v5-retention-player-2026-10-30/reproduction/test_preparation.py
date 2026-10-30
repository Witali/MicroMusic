"""Cost/admission and exact ordered-byte inventory contracts, no codec imports."""
import unittest

from prepare_retention import decision_from_rows, inventory_map


class PreparationContracts(unittest.TestCase):
    def row(self, identifier, score, size, eligible=True):
        return dict(id=identifier,score=score,stream_bytes=size,automatic_quality_eligible=eligible)

    def test_ineligible_raw_does_not_become_automatic(self):
        value = decision_from_rows([self.row(0,9,100),self.row(1,1,100,False)],100)
        self.assertEqual((value['selected_id'],value['raw_id']),(0,1))

    def test_cost_cap_and_stable_ties(self):
        rows = [self.row(0,1,110),self.row(1,2,100),self.row(2,2,100)]
        self.assertEqual(decision_from_rows(rows,100)['selected_id'],1)
        self.assertTrue(decision_from_rows(rows,99)['no_fit'])

    def test_noncontiguous_or_nonfinite_rows_fail(self):
        for rows in ([self.row(1,1,1)],[self.row(0,float('nan'),1)]):
            with self.assertRaises(ValueError):
                decision_from_rows(rows,100)

    def item(self, parts, contexts=None):
        context = dict(phase='speech-default',source_ordinal=0,profile=4,percent=100,mode='original')
        return dict(profile=4,parts=parts,contexts=[context] if contexts is None else contexts)

    def test_ordered_bytes_are_identity(self):
        value = inventory_map([self.item((b'a',b'b')),self.item((b'b',b'a'))],lambda row,_:row['parts'])
        self.assertEqual(len(value),2)

    def test_duplicate_bytes_or_contexts_fail(self):
        item = self.item((b'a',))
        for rows in ([item,item],[self.item((b'a',),item['contexts']*2)]):
            with self.assertRaises(ValueError):
                inventory_map(rows,lambda row,_:row['parts'])


if __name__=='__main__':
    unittest.main()
