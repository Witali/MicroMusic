import unittest
from recipe import cases,fields,old_positions


class Recipe(unittest.TestCase):
    def test_exact_finite_grid_and_order(self):
        for profile in (4,6):
            rows=list(cases(profile));self.assertEqual(len(rows),120)
            self.assertEqual([r['index'] for r in rows],list(range(120)))
            self.assertEqual((rows[0]['spectral_index'],rows[0]['scale'],rows[0]['mandatory_position'],rows[0]['original_extra_position']),(0,8,0,30))

    def test_target_changes_only_one_active_extra_position(self):
        for profile in (4,6):
            for case in cases(profile):
                base,target=fields(case),fields(case,True)
                self.assertEqual(base[:3],target[:3]);self.assertEqual(base[3][5][1],target[3][5][1])
                self.assertEqual(sum(x[1]!=0 for x in base[3]),1)
                self.assertEqual(sum(x[1]!=0 for x in target[3]),1)
                self.assertEqual(target[3][5],[target[2][10][0],-target[2][10][1]])

    def test_positions_deduplicate_and_bound_neighbors(self):
        self.assertEqual(old_positions(0,0),[0,1]);self.assertEqual(old_positions(39,39),[38,39])


if __name__=='__main__':unittest.main()
