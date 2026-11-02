# LPX v5: eliminate unreachable cosine interpolation

For centered 5/6-bit v5 LSF values, `lpx4LsfNorm10(prev,cur,t)` is a multiple
of 32 at polynomial anchors `t=0,8,16`. Thus only even nodes of the original
257-node Q13 cosine table are reachable, and the interpolation fraction is 0.
Keep 65 half-wave nodes 0, 2, ...128, reflect index `i>64` to `128-i`, read one
word and negate after reflection. Node 128 of the original table is zero.
The proof applies to compact-only segments 1/2; common formats and profile 6
quarter anchors with segments 4 retain the general helper.

Measured on ATmega328P/enhanced AVR5 with MUL, GNU ABI, AVR-GCC 7.3.0,
`-Os -flto -mcall-prologues -mrelax`, explicit ASM, unroll 1/tuning 0,
16 MHz/8 kHz, queue 512/prefill 384. This is a portable C specialization: the
existing C/explicit-ASM selection and manufacturer Flash headers are unchanged.
Original oracle/model tables remain independent of the new embedded table.

A 130 B direct table reduces complete Flash 56 B in six paired real firmware images.
An 80 B checkpoint/difference alternative saves only 34 B in its four-image screen:
measure table plus reconstruction code, rather than table bytes alone. Static
SRAM is unchanged. Available first 64000-sample decode statistics improve
2.286–2.521%; observed after-ready stack margin is one byte smaller. Complete
PWM is exact with active interrupts and zero underruns in 12 normal images plus
four selected +100 IRQ-cycle controls. No physical-board or universal speed claim.

Keep the full 4096-input generic helper regression, the frozen 34816-arbitrary-
anchor LPC fingerprint, and separate exhaustive legal-grid scalar/anchor tests.
Do not send arbitrary scalar bins/anchors through this reduced-grid helper.
[Source-bound measurements, rejected exact alternative and scope](../../Codecs/LPX/research/v5-grid-cosine-2026-10-28/README.md).

## Retain only reachable P4 nodes in a fixed-ROM SRAM512 build

The later Tiny88 recipe pins the speech flags and rejects mismatched input
headers. For P4 and segments 1/2, the existing node expression ends with a
left shift by one, so every index is even. Reflection `128-index` preserves
that parity. Keep entries 0,2,...,64 of the existing 65-word half-grid, then
use `index>>1` after reflection. This is an exact **33-word subset**, saving
64 table bytes; it does not round or quantize a new index. In original
257-node coordinates these are nodes 0,4,...,128.

The guard requires compact-only, SRAM512, fixed P4 flags and segments 1/2.
P6, unpinned headers and four-segment builds retain their prior tables/helper.
This is portable C specialization, shared by C and explicitly enabled ASM;
arithmetic backend and manufacturer Flash access selection stay independent.
The original oracle/model tables remain unchanged. Count the final lookup
instructions and linked layout as well as the 64 table bytes when reporting
complete Flash. The [Tiny88 budget entry](lpx-tiny88-budget.md) and its
source-bound receipt record the complete active-IRQ player scope separately
from the original AVR5 measurements above.

## Skip work on the implicit second spectral half

The existing compact-only `!speechHalf_` branch can also own the `cur_→prev_`
LSF copy. The second half uses its cached endpoint and the next first half
refreshes previous LSFs before delta decoding. Keep common-format behavior,
partial tails, all segment modes, bandwidth expansion and snapshots intact.

Against the direct-cosine baseline, six complete images save another 14 B
(single segment) or 152 B (two/five segments); this difference includes linked
inlining/layout effects. Static SRAM is unchanged; observed stack margin
improves by four/six bytes. Six normal and four +100 IRQ-cycle final images
produce exact complete model PWM with zero underruns. Available decode
statistics improve 0.156–2.284%, scoped to at most the first 64000 samples.
[Separate experiment, regression matrix and limitations](../../Codecs/LPX/research/v5-half-spectrum-2026-10-28/README.md).
