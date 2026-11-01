# Exact allocation over fixed reset pools

`speech_chain_rate.allocate_exact_sse` is an opt-in, codec-free multiple-choice
allocator. It combines one existing serialized option per reset. It does no
fitting or decoding, and leaves the generic objective/default behavior of
`speech_chain_frontier.assemble` unchanged.

Supply nonempty per-reset rows with stable nonnegative integer `id`, actual
`stream: bytes` and verified integer PCM `sse`. The caller must independently
verify the target, reset geometry, stream/model/native output and local SSE.
Rate is always the actual sum of stored lengths; distortion sums use Python
integers. Identical bytes cannot have inconsistent scores. Equal rate/SSE ties
use lexicographic ID tuples.

Sparse dynamic programming keeps minimum SSE at each exact byte sum and removes
states dominated in bytes/SSE. A prefix is also removed if even the cheapest
remaining suffix cannot fit. This is valid because decoding resets between
segments and PCM squared errors add across the complete concatenation. No
proportional reset budgets, proxy encoded lengths or frontier sampling are used.
One complete run at B answers every smaller cap by filtering its final frontier.

`baseline_ids` and `protected_chains` independently retain whole tuples, including
oversized or SSE-dominated ones. They are never silently discarded because the
DP does not prefer them. Preserve every previous whole recipe/incumbent too.
The exact frontier is only for additive PCM SSE/rate over the supplied pools;
it is not an exact optimum under whole PWM, STOI, F0/period, voice/noise, clipping
or joint quality gates. Those require fresh complete-record evaluation. A raw
SSE improvement or a no-fit in these finite pools establishes no audible claim.

The default bounds are 250,000 distinct working byte states per layer before
pruning and 10,000,000 visited prefix/option transitions, including size-pruned
ones. Exceeding either returns `state_limit`/`transition_limit`, `exact=False`,
`best=None` and an empty exact frontier; it does not report no-fit. Counters
separate created states, peak working-layer size, completed reset layers,
pruned states/transitions and completed full candidate publications. Peak layer
size is not a process-memory measurement or a combined live-layer count.

An optional `checkpoint()` runs before every transition. An optional
`on_candidate(point)` immediately receives each improved feasible final-layer
byte state, before the next checkpoint/state guard. Points are immutable full
ID tuples with total bytes/SSE. No partial prefix is published. These complete
choices can be retained even if the next atomic step fails. Exceptions propagate;
the callback consumer owns persistence, native verification and whole admission.

Tests compare complete frontiers with exhaustive Cartesian enumeration, including
mixed allocations missed by extreme recipes, exact large integer differences,
deterministic ties, protected choices, no-fit and interrupted publication. These
are algorithm contracts, not corpus quality or firmware Flash evidence.
