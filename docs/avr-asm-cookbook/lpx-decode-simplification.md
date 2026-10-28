# Systematic exact decoder simplification

LPX v5-only experiments start from `3f717df5`, whose C++ decoder matches
`4b399def`. Target measurements use ATmega328P / AVR5 with MUL, GNU ABI,
AVR-GCC 7.3.0, `-Os -flto -mcall-prologues -mrelax`, unroll 1/tuning 0,
16 MHz / 8 kHz, queue 512/prefill 384 and explicit ASM. The algorithms remain ordinary
C++; Flash access and arithmetic backend selection stay independent. No new
assembly, format or approximate arithmetic is implied by this catalogue.

## Choose a proof before choosing a rewrite

| Method | Concrete LPX opportunity | What must be proved | Current status |
| --- | --- | --- | --- |
| Use reachable input ranges | Bounded header subtraction; signed8 spectrum temporaries; remove compact position recheck after pair<400 | Every rejected/truncated input still has identical error, read order, metadata and output | Selected bounded subtraction/signed8 arithmetic; packed flags save 1 SRAM byte; see integrated results |
| Use the actual quantization grid | v5 profiles4/6 with LPCsegments1/2 need only even cosine nodes and zero fraction | Every transmitted previous/current pair at all reachable anchors, reflection and partial tails | Selected direct130 B table:56 B isolated image saving;80 B alternative rejected |
| Exploit exact integer symmetry | Keep only reciprocal P polynomial's first half | Every retained rounded product has identical mirrored operands; final reconstruction exact | Exact but rejected:+70..160 B Flash for up to24 B scratch saving |
| Replace known unit products | polyFactor trailing coefficient stays+/-4096 | Unit survives every factor; negation widened before signed16 minimum | Selected:564288 compiled factors exact;0..2 B isolated saving and lower decode time |
| Respect scheduling boundaries | Skip ten-word previous-LSF copy on the second160-sample half | No consumer reads that previous spectrum before next first-half refresh | Selected:360input matrix and36snapshots exact;14/152 B isolated image saving |
| Keep encoded representation longer | Store compact LSF indices as bytes, dequantize at synthesis | All profiles/anchors, invalid packets, reset/copy and common layout | Exact87040-scalar norm identity; deferred behind smaller changes |
| Encode mutually related state once | Merge compact profile/extras flags or half/subframe phase | All flags, error precedence and20/160/320-tail validation timing | Compact format flags selected; half/subframe phase remains deferred |
| Reorder bounded sparse insertion | Two base pulses occupy disjoint20-sample halves | Every base/extra position, collision amplitude and saturation order |Rejected mixed image result:+26/-124 B; source patches retained |

Expression proofs are not native/AVR admission. The experiment branches isolate
changes so a shorter expression or fewer arithmetic operations is not mistaken
for smaller linked firmware. Retain source snapshots and rejected measurements;
compare the combined selected implementation again because LTO savings are not
additive.

## Quantized cosine grid

A transmitted compact LSF is `(q<<s)+(1<<(s-1))`, s5/4. At default anchors
`t=0,8,16`, let u=t/8. The exact cosine node index is
`(profile4 ? 4 : 2) * (previousQ*(2-u)+currentQ*u+1)`. It is even and the
fractional interpolation remainder is zero. General formats and profile6 with
four LPC segments can use other nodes and keep their generic implementation.

Two exact candidates deserve measurement:65 direct signed16 half-wave nodes
(130 B), or eight signed16 checkpoints plus64 unsigned8 first differences (80 B,
at most seven additions; node128 is exactly zero). The larger direct table can
win total Flash if it removes more code. Original257-node cosine data remain
the independent oracle; generated tables must ignore comments and verify entry
count/provenance. Do not publish a table-only byte count as an image saving.

## Integer symmetry has to survive rounding

P begins with1+z and multiplies reciprocal quadratics1+c*z+z². Mirrored P
coefficients remain exactly equal: both sides use the same rounded middle
product and the same outer summands. Its first six coefficients determine the
final degree11 polynomial. A half recurrence can reduce24 P products to10 and
save24 scratch bytes; emitted code may still grow.

Q is anti-reciprocal only over real arithmetic. Under signed floor rounding,
`floor(-x)` need not equal`-floor(x)`. Do not derive its missing half by negation.
Do not reorder or combine rounded products just because a symbolic real-valued
identity permits it. Preserve final clamps and the wide polyMulQ12 path: valid
clustered spectra already exceed its fast-path coefficient bound250000.

## Store less only when the lifecycle permits it

For compact quantized previous/current P,C and0<=t<=16, define
`W=16*P+(C-P)*t`. Exact normalized phase is
`(W<<(s-2))+(1<<(s+1))`; no fractional loss occurs for s>=4. This supports a
byte-storage experiment without changing the stream. Copies, member layout,
restart/error state and native-cache source inventories are part of correctness.

Conversely, valid n<=64000 alone does not justify narrowing public sample
metadata: failed begin() stores untrusted32-bit counts before rejecting them,
and later short/null begin() retains previous metadata. A state reduction needs
an explicit equivalent lifecycle, not only a valid-audio range proof.

## Measurement and retention

Run compiled helper/golden checks, differential malformed streams and copies,
then frozen whole-corpus PCM/PWM in common and v5-only layouts. Exercise LPC
segments1/2/4 and explicitly selected C fallback. For a claimed target profile,
compare complete linked images with identical data/reset geometry and verify
full output plus underruns under active IRQ. Scope the existing runner's64000
sample decode-duration window separately from full playback verification.

The combined selected source was checked on all 181 frozen cases and all 111
unique normal current selections, plus five additional IRQ controls. Full Flash
falls 110 B(single-segment) /246 B(chains), static SRAM falls 1 B, and profiled decode
cycles fall 5.258% over 4,914,100 timed samples. Complete PWM and underruns are
verified for every chain;12 long controls explicitly scope duration statistics
to the first64000 calls. 55 targeted tests and 605670 ASan/UBSan cases per layout
pass. [Integrated measurements, scopes and rejected alternatives](../../Codecs/LPX/research/decoder-simplification-2026-10-28/README.md).

Useful rejected ideas belong here as evidence, not dormant production code. [Earlier measured techniques](lpx-program-flash.md) explain
already-tried in-place recurrences, compact tables and bounded arithmetic.


## Completed source-audit iteration

The [action plan](../../Codecs/LPX/NEXT_OPTIMIZATION_PLAN_RU.md) is complete:
every item was implemented or checked with measured rejection evidence.
Do not retain rejected prototype branches in the production decoder.
The methods and their range/lifecycle proofs remain below and in the linked
experiment archive; a result from a local screen does not replace final IRQ
and corpus admission.

## Measured byte-grid and private-count follow-up

For v5-only, store q+1 (1..32/64) and reserve0 for untouched fields. At
segments1/2 anchors u=t/8, the exact even-table index is
`(P*(2-u)+C*u-1)*(profile4 ? 2 : 1)`. Factor directly to the table index:
reconstructing a wide normalized coordinate and immediately shifting it back
costs code on AVR. Keep the full centered conversion for quarter anchors in
segments4, and normalize private probes to preserve semantic frozen oracles.
Eight fixed full diagnostic images save100 B Flash and20 B static SRAM.

Keep untrusted public sample metadata wide. A compact private uint16 remaining
is sufficient only with explicit modulo16 subtraction before produced widens;
this preserves zero progress after invalid/null/short begins as well as valid
counts. Standalone linked savings are74..78 B Flash and2 B SRAM. Combined
with byte-grid LSF, measured savings are174..176 B and22 B respectively.
These independent screens use AVR-GCC7.3.0, ATmega328P/AVR5, GNU ABI,
`-Os -flto -mcall-prologues -mrelax`, LPC segments2, unroll1/tuning0,
explicit ASM and identical streams/reset geometry.56 core regression tests
plus the new frozen lifecycle/count probe pass. Final campaign IRQ/corpus admission is now complete for the selected
combination; individual rejected prototypes retain only their stated scope. [Source patches, proofs and measurements](../../Codecs/LPX/research/v5-plan-execution-2026-10-28/README.md).


## Final source and application admission, 2026-10-28

Decoder source5c7e0592 reduces the same diagnostic images by218..222 B Flash
and45 B static SRAM. All111 normal plus5 extra100-cycle IRQ controls have
complete duration coverage, exact full PWM and zero underruns/errors. Normal
mean decode wall time rises5.619%, a measured size/time tradeoff with retained
headroom. The raw32-bit public sample metadata, common formats, C
fallback and explicit real supported-target ASM selection remain intact.

The separate standalone256/prefill192 player ends at4573..4600 B program
Flash (only proven embedded audio arrays subtracted) and756 B static SRAM.
Actual combined savings versus fixed-b8 diagnostic512 controls are410..498 B
Flash and328..329 B SRAM. These are measured pairs, not added LTO estimates:
the same core change saves only182..184 B inside the standalone application.
Startup/prefill/playback stack observation gives1231 B minimum margin; full
PWM/ticks/EOF, buffer publication and zero underruns pass all116 images.
The128 profile grows Flash6 B and is rejected before timing admission.

ATmega328P/AVR5 GNU ABI, AVR-GCC7.3.0,16MHz/8kHz, LPC segments2,
`-Os -flto -mcall-prologues -mrelax`, unroll1/tuning0 and explicit ASM.
Native common/v5-only/model/frozen PCM/PWM agree on181 cases/1224 streams;
204 whole-chain metrics are freshly exact;1255140 ASan/UBSan mutation/reset
cases pass. These are simulator and host results, with no physical-board or
analog-output claim. No new arithmetic assembly kernel was introduced.
[Complete admission and source-only experiment archive](../../Codecs/LPX/research/v5-plan-execution-2026-10-28/README.md),
[external player/observer method](lpx-release-player.md).
