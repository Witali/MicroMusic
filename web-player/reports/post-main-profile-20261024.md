# Sampling after the common AVR integration

The retained runtime is `111f314fdbab5bd7a8f1c0c4d8891811676e436bd7aa78681d6c62728ef0fba6`
from the common-core integration. Production source and WASM are unchanged.
This refresh implements the next profiling step in the optimization plan.

There are 24 fresh-state profiles across eight cases, with 20,231 samples
inside public execution/capture stacks. Three real firmware images run in
both compatible and physical/resumable modes: 48,000 frames at 48 kHz, three
repeats each. Two direct arithmetic kernels run one million instructions per
repeat. Lowering, compilation, setup, warmup, hashing and output comparisons
stay outside sampling. The named native rebuild matches every production byte;
each profiled run matches the production PCM and final architectural snapshot.

On the six real-firmware cases, `next_event` accounts for 7.7–9.6% of leaf
samples, `ratio` for 8.7–9.7%, and `duration` for 6.1–8.4%. These are surviving
optimized function bodies, including any inlined work. They identify repeated
event/time conversion as the next experiment. They do not establish exclusive
peripheral costs, a causal speed regression or a predicted speedup. The direct
kernels have only 180/262 samples; their rankings are less informative.

The profiler now resolves catalog aliases and records requested and actual
firmware IDs separately. The former `hq4-chego-auto` default selects the current
`hq4-chego-tiny` image; its firmware hash is retained. Alias resolution must not
silently profile the same image twice. New shared profile metadata and catalog
inputs are included in the source hashes.

[Analysis](post-main-profile-20261024/analysis.json) contains all pooled frames,
categories, raw-profile hashes and reproduction commands. The four adjacent
JSON summaries preserve original run counts, sample deltas, provenance and
production parity. Raw `.cpuprofile` files remain under the ignored
`build/profiles/post-main-7ae9443/` directory, following the profiler's existing
artifact policy. Profiled elapsed times are not benchmark results. No candidate
is retained and no speedup is claimed here.

The next candidate must preserve integer remainders, clock changes, input/event
ordering, IRQ/reset boundaries and physical pin/PCM timestamps. Use separate
uninstrumented balanced identical-runtime controls before accepting it. CLKI
and enabled-ADC controls remain required for any scheduling optimization.
Continuation liveness remains a separate compiler candidate. Stage 5 stays open;
the main hardware checklist remains 21/30.
