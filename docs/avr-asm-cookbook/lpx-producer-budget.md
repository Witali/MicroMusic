# Measure decoder work without changing the AVR application

Applicable target: ATmega328P / AVR5, two-byte PC, GNU AVR ABI, AVR-GCC 7.3.0,
16 MHz / 8 kHz, explicit existing ASM arithmetic and selectable C fallback.
Production flags are `-Os -flto -mcall-prologues -mrelax`, dot-unroll 1,
function-tuning 0, queue 256 / prefill 192. This is an original host-observation
technique; it adds no AVR instructions, state, markers or profiler tables.

Fixed-rate timer playback remains 8 kHz even when decoder work changes. Do not
use its elapsed duration or empty polling-loop iterations as a CPU measure.
The external observer resolves the unique linked `produce()` ELF function,
checks its entry, stack and stacked two-byte return address, and terminates
each body at its actual `RET`. The body includes queue/EOF publication and
four RET cycles; caller CALL and idle polling are outside the interval.
Actual head publication separates useful output calls from failed, EOF-only
or queue-full calls. Preload, steady playback and terminal publication are
counted separately, and useful calls must match all produced/played samples.

Both interval endpoints are outside IRQ context. Subtract the complete live
IRQ notification intervals **and actual measured RETI instruction steps**.
The latter correction matters because simavr 1.6 lowers RUNNING before RETI's
cycles are charged: see the pinned [interrupt notification implementation](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/sim_interrupts.c)
and [RETI/RET instruction implementation](https://github.com/buserror/simavr/blob/v1.6/simavr/sim/sim_core.c).
This avoids partly subtracting an ISR at a body boundary. It does not change
simavr's hardware model or establish physical-board interrupt timing.

Record each useful call's wall/IRQ cycles. Independent array sums and
convolutions audit total, maximum, and worst consecutive 160/320-call work
windows against the streaming observer. Refuse absent/ambiguous function
symbols, invalid return boundaries, counter inconsistencies or lost output.
This measures the actual production producer, including necessary publication
overhead, rather than claiming a pure mathematical-kernel cost.

The production image still passes the separate exact PWM, timer, queue drain,
stack and underrun observer. A 20% work allowance requires a meaningful sound
gain as well; a small parser or a passing real-time timer alone is insufficient.

## Measured raw-scale ramp probes

Explicit version 10 keeps the existing v5/P4 or sparse80 payload and introduces
raw amplitude-step interpolation at 20-sample boundaries. Interpolating table
indices would change its meaning; instead cache
`(previous*(8-k)+target*k+4)>>3`, for k = 1..8, then apply existing Q4 caching.
The first tuple initializes both endpoints, including raw zero. Sparse80 holds
the target during its second 160 samples. Signed16 bounds avoid wide arithmetic.
Two dedicated cold uint16 endpoints add 4 AVR SRAM bytes; synthesis arithmetic
per sample, hardware definitions and C/ASM selection remain unchanged.

On one unchanged 2.4-second payload at each cap, cost-only probes give:

| Payload | Mean producer cycles/sample | Worst160/sample | Worst320/sample | Full Flash | Static SRAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| sparse80 ordinary | 816.666 | 920.769 | 842.841 | 5458 B | 756 B |
| sparse80 raw-step ramp | 818.869 | 922.019 | 844.325 | 5774 B | 760 B |
| v5/P4 ordinary | 767.730 | 912.494 | 833.084 | 5474 B | 756 B |
| P4 raw-step ramp | 785.072 | 929.938 | 850.463 | 5896 B | 760 B |

All four complete 19,200-sample active-IRQ runs reproduce their independent
model PWM exactly with zero underruns and boundary errors. Mean work grows
about 0.27% / 2.26%; Flash grows 316 / 422 B. These demonstrate cost, **not sound
benefit or adoption**. The subsequent ramp-aware tuning pilot retained the
protected incumbents at both budgets, so the ramp was rejected before a corpus
run. Native C Q0/Q4 paths, all final packet tails, maximum sample
counts, malformed input, copied/reset decoders and old-format opt-ins have
18 passing direct-contract tests. With both experiments disabled, ordinary
v5 and sparse80 firmware remain byte-identical to the original source.

The earlier metadata320 route met a provisional CPU allowance but all 25 new
tuning candidates failed the protected quality guards, so it was rejected
before a corpus run. Its original v1 timing receipts retain the explicitly
labelled conservative RETI residual; they are not the final v2 budget gate.
[Anonymous measurements and scope](../../Codecs/LPX/research/meta320-lowrate-2026-11-02/decoder-costs.json)
preserve useful negative evidence without claiming a completed corpus round.
Both decoder prototypes remain default-off in the isolated decoder-budget
branch. The final quality branch retains the existing decoder.

## Reproduce locally

`build_release_observer.py --producer` builds the external observer from
`validation/atmega328p/sim_producer.c`, which reuses the existing playback
observer. `profile_release_producer.py` builds and verifies a complete image
and audits every measured producer call. Use `--scale-ramp`, plus `--sparse80`
for version 10/mode15, or `--meta320` for the separate version9 prototype.
An explicit independent oracle is required for optional formats in the lower
level production builder. All media, ELF files, traces and source/toolchain
fingerprints remain in ignored `build/`. No publication or flashing occurs.
