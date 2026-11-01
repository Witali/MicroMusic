import math
import unittest
from unittest.mock import patch

from search_cpu_budget import CpuBudget, CpuBudgetExceeded


class CpuBudgetTests(unittest.TestCase):
    def setUp(self):
        self.cpu, self.wall = 10., 100.
        cpu = patch('search_cpu_budget.time.process_time', side_effect=lambda: self.cpu)
        wall = patch('search_cpu_budget.time.perf_counter', side_effect=lambda: self.wall)
        cpu.start()
        wall.start()
        self.addCleanup(cpu.stop)
        self.addCleanup(wall.stop)

    def test_invalid_limits_fail_before_starting_clocks(self):
        for value in (True, False, -1, math.inf, -math.inf, math.nan, '2', [], 10**1000):
            with self.subTest(value=type(value).__name__), patch(
                    'search_cpu_budget.time.process_time', side_effect=AssertionError('not started')):
                with self.assertRaises(ValueError): CpuBudget(value)

    def test_validation_normalizes_without_starting_clocks(self):
        with patch('search_cpu_budget.time.process_time', side_effect=AssertionError('not started')), patch(
                'search_cpu_budget.time.perf_counter', side_effect=AssertionError('not started')):
            self.assertEqual(CpuBudget.validate(2), 2.)
            self.assertEqual(type(CpuBudget.validate(2)), float)
            self.assertIsNone(CpuBudget.validate(None))
            with self.assertRaises(ValueError): CpuBudget.validate(True)

    def test_cpu_not_wall_and_exact_limit_stops_next_work(self):
        budget = CpuBudget(2)
        self.cpu, self.wall = 11.5, 1000.
        budget.check()
        self.assertFalse(budget.exhausted)
        self.cpu = 12.
        with self.assertRaises(CpuBudgetExceeded): budget.check()
        self.assertTrue(budget.exhausted)
        self.assertEqual(budget.checks, 2)

    def test_zero_limit_expires_at_first_checkpoint(self):
        budget = CpuBudget(0)
        with self.assertRaises(CpuBudgetExceeded): budget.check()
        self.assertEqual(budget.report()['limit_seconds'], 0.)

    def test_none_keeps_search_enabled_and_has_no_overshoot(self):
        budget = CpuBudget()
        self.cpu, self.wall = 1000., 2000.
        budget.check()
        result = budget.report()
        self.assertIsNone(result['limit_seconds'])
        self.assertFalse(result['exhausted'])
        self.assertEqual(result['cpu_overshoot_seconds'], 0.)
        self.assertEqual(result['search_cpu_seconds'], 990.)
        self.assertEqual(result['finalization_cpu_seconds'], 0.)

    def test_finish_is_idempotent_and_accounts_finalization_separately(self):
        budget = CpuBudget(2)
        self.cpu, self.wall = 12.25, 103.
        with self.assertRaises(CpuBudgetExceeded): budget.check()
        budget.finish_search()
        self.cpu, self.wall = 13.5, 108.
        budget.finish_search()
        budget.check()
        result = budget.report()
        self.assertEqual(result, dict(limit_seconds=2., checks=1, exhausted=True,
            search_cpu_seconds=2.25, finalization_cpu_seconds=1.25, total_cpu_seconds=3.5,
            search_wall_seconds=3., finalization_wall_seconds=5., total_wall_seconds=8.,
            cpu_overshoot_seconds=1.5))

    def test_natural_completion_can_overrun_without_observed_exhaustion(self):
        budget = CpuBudget(2)
        budget.check()
        self.cpu, self.wall = 12.5, 103.
        budget.finish_search()
        result = budget.report()
        self.assertFalse(result['exhausted'])
        self.assertEqual(result['cpu_overshoot_seconds'], .5)


if __name__ == '__main__':
    unittest.main()
