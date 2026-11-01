# Matched-search complete ROM player results

The finite changed-selection union passed the complete ROM player gate for every
chain that fits in the ATmega328P's internal Flash: 362 passing IRQ rows, with no
timing or output failure. Twelve rows are data-alone no-fits and make no playback
admission claim. This is a feasibility result for saved numerical selections;
it does not establish audible preference or choose a new default search arm.

The [final scope](final-scope.json), [aggregate](summary.json), [anonymous rows](rows.json),
[cost projection](cost-summary.json) and [strict artifact check](artifact-check.json)
record the result. [Source/runtime provenance](source-runtime.json) and the
[reproduction source receipt](reproduction/sources.json) bind the implementation.
The [protocol](PROTOCOL.md) predates image execution.

## Scope and completed proof

The numerical prerequisite contains 248 arm records, 312 helper calls and 744 cap
views over 104 common baseline contexts. Its 112 changed automatic selection
views deduplicate to 105 ordered candidate chains. Pairing them with 82 strongest
same-level canonical rollback chains gives 187 distinct chains, with no role
overlap. Unchanged views are excluded from this image union. Arm, tier and cap
views overlap; they are not independent recordings. The cumulative 2+8-second
views retain the earlier candidates and charge the earlier helper work.

| Result | Candidate rows | Rollback rows | Total |
| --- | ---: | ---: | ---: |
| Declared IRQ rows | 210 | 164 | 374 |
| Passed | 202 | 160 | 362 |
| Newly built and simulated | 202 | 108 | 310 |
| Strict prior proof reuse | 0 | 52 | 52 |
| Data-alone no-fit | 8 | 4 | 12 |
| Timing or output failure | 0 | 0 | 0 |

Every chain is evaluated at IRQ loads 0 and +100 cycles. The 12 no-fit rows are six
full 60-reset long nonspeech chains whose stored data already exceeds 32768 bytes;
no forced oversized ROM image, truncation or reset removal is used. There are no
linked-Flash overflows in the admitted-size portion of this union.

The strict final exporter reopens exact ordered stream bytes and the complete
source/compiler/runtime/image proof, rechecks model/common/v5 PCM16 and PWM, and
checks physical PWM output, EOF, sample counts, timer ticks/events, drained queue,
stack margin and zero underruns or decoder/observer errors. It performs no new
AVR build or simulation. The aggregate and final read-only export both completed
with observed exit code 0.

The proof covers 15,753,700 physical PWM samples: 13,840,482 from newly simulated
images and 1,913,218 from strictly reopened prior proofs. A reused sample is not
counted as a new simulation.

## Complete Flash and working memory

There are 105 candidate/rollback comparisons per IRQ load. For each load, both
images pass in 101 comparisons; four long comparisons cannot be admitted to ROM.
Among the 101 admitted comparisons, eight candidates save complete Flash, 93 are
equal and none is larger. The savings are four bytes in one comparison and two
bytes in each of seven comparisons. These counts are identical for both IRQ
loads; do not sum them as distinct audio cases.

Complete Flash includes stored streams, reset metadata, tables and program.
Program Flash excluding stream bytes ranges from **4573 to 4600 bytes** across
the 362 admitted rows. Its candidate-minus-rollback change ranges from -1 to +1
byte because image layout can change even when stored data shrinks. Stream-only
savings therefore do not necessarily reduce complete Flash.

The largest admitted image in this union uses **20742 bytes of complete Flash**:
16142 stream bytes and 4600 remaining bytes, for a five-reset profile-4 chain
with 281632 samples at IRQ +100. This is the maximum of the changed-selection
union, not a maximum over unchanged or earlier corpus contexts. Static SRAM is
756 bytes in every passing image; the smallest observed all-stack margin is
1231 bytes.

## Preserved host failure and bounded recovery

One original worker exited with code 1 after 91 passing rows: Windows error 5
prevented atomic journal replacement before the next image operation. Its failed
journal and receipt remain intact, and the pending event has no original image
directory. The other original worker completed unchanged with observed exit 0.
The earlier preparation's terminal artifacts were present when ownership passed;
its expired execution handle supplies no observed exit code.

A separately bound recovery strictly reopened the 91 completed proofs, then
processed only the 97 original pending rows: 83 new images, eight prior reuses and
six no-fits. It completed with observed exit 0. No completed simulation was
repeated. The narrowly bounded replacement retry applies only to Windows errors
5/32, with at most six attempts and preserved incomplete writes on final failure;
the successful recovery needed zero actual retries. A competing periodic metadata
reader was disabled before recovery; whether it caused the original access denial
is unknown. Final receipts retain three worker attempts and one pre-image host
filesystem failure rather than rewriting the original attempt as successful.

## Limits

The consumer is the frozen v5-only player/core source recorded as `5b4800f7`;
producer primitives are pinned to `df8443cc389f1298ab23a3aca9cdee15e781bbe0`.
The measured player uses explicit AVR ASM at 16 MHz/8 kHz, a 256-byte queue and
prefill 192 in the pinned simavr observer with interrupts active. The selectable
C fallback remains available but has no timing admission from this campaign.
No decoder source or firmware algorithm is changed by this stage.

Original-level and declared amplified-level references retain their separate
same-level rollback bindings. This gate does not compare SSE across those levels,
rerun fitting, infer perceptual gains from rollback or no-fit outcomes, or prove
board/analog behavior. External SPI playback, listening, held-out voice evaluation
and future rate allocation are separate evidence and work items.
