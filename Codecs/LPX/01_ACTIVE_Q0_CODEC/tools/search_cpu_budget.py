"""Optional cooperative host CPU quota with explicit finalization accounting.

A quota limits setup and search at caller-selected safe checkpoints. It is not
a hard deadline: an in-flight operation completes before the next check, and
final verification remains outside the quota. Process CPU includes native work
and every thread in this process; wall time is reported independently.
"""
from __future__ import annotations

import math
from numbers import Real
import time


class CpuBudgetExceeded(Exception):
    """The next search operation must not start after the CPU quota expires."""


class CpuBudget:
    @staticmethod
    def validate(seconds):
        """Normalize a quota without starting clocks or doing search work."""
        if seconds is not None:
            if isinstance(seconds, bool) or not isinstance(seconds, Real):
                raise ValueError('Expected a finite nonnegative CPU quota or None')
            try:
                seconds = float(seconds)
            except (OverflowError, ValueError):
                raise ValueError('Expected a finite nonnegative CPU quota or None') from None
            if not math.isfinite(seconds) or seconds < 0:
                raise ValueError('Expected a finite nonnegative CPU quota or None')
        return seconds

    def __init__(self, seconds=None):
        self.limit_seconds = self.validate(seconds)
        self.checks = 0
        self.exhausted = False
        self._cpu_started = time.process_time()
        self._wall_started = time.perf_counter()
        self._search_cpu_finished = None
        self._search_wall_finished = None

    def check(self):
        """Stop before a new operation; never interrupt a completed contender."""
        if self._search_cpu_finished is not None:
            return
        self.checks += 1
        if (self.limit_seconds is not None
                and time.process_time() - self._cpu_started >= self.limit_seconds):
            self.exhausted = True
            raise CpuBudgetExceeded

    def finish_search(self):
        """Freeze setup-plus-search time once; later work is finalization."""
        if self._search_cpu_finished is None:
            self._search_cpu_finished = time.process_time()
            self._search_wall_finished = time.perf_counter()

    def report(self):
        """Snapshot actual elapsed work, including any quota overrun.

        cpu_overshoot_seconds uses total helper CPU, including finalization.
        Search-only overrun is max(0, search_cpu_seconds - limit_seconds).
        A naturally completed search need not observe exhaustion at a check.
        """
        cpu_now, wall_now = time.process_time(), time.perf_counter()
        search_cpu_end = cpu_now if self._search_cpu_finished is None else self._search_cpu_finished
        search_wall_end = wall_now if self._search_wall_finished is None else self._search_wall_finished
        total_cpu = cpu_now - self._cpu_started
        return dict(limit_seconds=self.limit_seconds, checks=self.checks, exhausted=self.exhausted,
            search_cpu_seconds=search_cpu_end - self._cpu_started,
            finalization_cpu_seconds=cpu_now - search_cpu_end, total_cpu_seconds=total_cpu,
            search_wall_seconds=search_wall_end - self._wall_started,
            finalization_wall_seconds=wall_now - search_wall_end,
            total_wall_seconds=wall_now - self._wall_started,
            cpu_overshoot_seconds=(0. if self.limit_seconds is None
                                   else max(0., total_cpu - self.limit_seconds)))
