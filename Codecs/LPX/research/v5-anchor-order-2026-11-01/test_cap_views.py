"""Reject missing, repeated, reordered or mis-sized saved cap views."""
import copy
import unittest
from cap_postcheck import validate_cap_rows


def rows():
    return [dict(id=i,baseline_bytes=1000,whole_caps={'100':1000,'95':950,'90':900},
        decisions=[dict(percent=p,cap=p*10) for p in (100,95,90)]) for i in range(48)]


class CapViews(unittest.TestCase):
    def test_actual_count(self):self.assertEqual(validate_cap_rows(rows()),144)

    def test_same_count_cannot_hide_repeated_or_reordered_percentages(self):
        for percentages in ([100,100,90],[90,95,100],[100,95]):
            values=rows();values[0]['decisions']=[dict(percent=p,cap=p*10) for p in percentages]
            with self.assertRaises(ValueError):validate_cap_rows(values)

    def test_duplicate_row_and_wrong_real_byte_cap(self):
        values=rows();values[-1]['id']=0
        with self.assertRaises(ValueError):validate_cap_rows(values)
        values=rows();values[2]['decisions'][1]['cap']=951
        with self.assertRaises(ValueError):validate_cap_rows(values)


if __name__=='__main__':unittest.main()
