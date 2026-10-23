# ATtiny13A sleep wake-up with a stopped or irregular source clock

The optional edge-driven sleep API models startup CK and wake CPU cycles without
converting them into a guessed frequency. The existing deadline-based sleep API
and clock-domain policy remain available unchanged. Time units belong to the
caller; the physical board uses integer picoseconds.

## Contract

`system_sleep_wake_clocked(s, asserted, enabled, int0_level_sense, source_ck,
extra_cpu_cycles, recovery_ticks, now)` returns the existing sleep result flags.
Wake masks, reset priority and CPU ownership of later interrupt arbitration are
unchanged. `extra_cpu_cycles` must equal four. `source_ck` must be zero for Idle
and ADC Noise Reduction; the board selects the documented/profiled power-down
startup count. The API does not derive a count from fuses or a clock frequency.

Source startup CK and wall-time recovery run concurrently. For example, an
explicit BOD recovery hold does not become a count of source-clock edges.
`STARTING` ends only when both `source_ck_left == 0` and `recovery_until` has
elapsed. Four actual system rising edges then consume `wake_cycles_left` in
`WAKE_DELAY`. No amount of wall-time advance substitutes for a missing edge.
Power-down keeps MAIN off during STARTING and enables it during WAKE_DELAY;
Idle and ADC Noise Reduction retain their existing domain policy.

Call `system_sleep_clock_edge(s, source_rising, system_rising, now)` with actual
rising-edge indications. Separate source/system calls at one timestamp are
allowed. An edge at the wake-request timestamp is excluded. The timestamp that
completes STARTING cannot also consume a wake cycle; repeated rising-edge
reports for the same domain and timestamp count once. These explicit scheduler
ordering conventions prevent a cause edge or a startup edge being counted
twice; the datasheet does not specify these software call boundaries.

`system_sleep_advance` handles a known wall recovery deadline without inventing
edges. It records the actual recovery boundary, so a later first system edge is
counted. `system_sleep_next_event` returns only a future wall recovery deadline;
unknown source/system-edge waits return UINT64_MAX. The caller must schedule
source and system edges separately. `ready_at` becomes known on the fourth wake
edge, and `wake_delay_at` records the startup/recovery completion boundary.
`startup_until` is unknown while source CK remain. `source_ck_left`,
`wake_cycles_left`, and `clocked` are observable state fields, not CPU opcodes.

Backward time, an invalid cycle count, nonzero Idle/ADC startup CK, and a wall
deadline reaching or exceeding reserved UINT64_MAX reject an eligible wake
before state mutation. Reset cancels counters. A new sleep clears edge-driven
state so legacy callers cannot inherit it. No allocations or host callbacks are
used. Interrupt entry's separate four cycles remain owned by the CPU backend.

## Official basis and profile boundaries

Source: [Microchip ATtiny13A datasheet DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
Section 6.2.1, Table 6-3 (printed p31) gives six CK power-down startup for the
external clock; sections 6.2.2/6.2.3, Tables 6-5/6-6 (p32) give six CK for the
internal sources. These CK are source edges, rather than a universal elapsed
time. Fuse-dependent reset startup and its additional WDT-timed delays are
separate board responsibilities.

Section 7.1 (p36) adds four cycles to interrupt wake-up, in addition to startup.
Sections 7.1.1–7.1.3 (pp36–37) describe stopped domains and eligible sources for
Idle, ADC Noise Reduction and Power-down. Section 7.2 (p37) describes the BOD
re-enable hold after software sleep-disable, approximately 60 microseconds.
The caller supplies its explicit recovery profile; that typical analog delay
is not asserted as an exact property of every physical chip.
