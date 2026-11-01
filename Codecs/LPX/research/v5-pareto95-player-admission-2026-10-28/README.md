# Held-out v5 Pareto point: complete-player admission

One fixed evaluation profile-4 recording preserves all original PCM/PWM
error-energy and STOI floors while reducing the complete stream from
1,800 to 1,701 B. It fits the original 95% cap of 1,710 B. Fresh complete
reference metrics and common/v5-only native/model PCM/PWM reproduce the
campaign handoff exactly. This verification uses the already selected point;
no search settings are retuned on it.

| Production player | Original | Selected | Selected minus original |
|---|---:|---:|---:|
| Full Flash, normal IRQ | 6,374 B | 6,274 B | -100 B |
| Full Flash, extra 100 IRQ cycles | 6,382 B | 6,282 B | -100 B |
| Program Flash excluding exact audio, normal | 4,574 B | 4,573 B | -1 B |
| Program Flash excluding exact audio, stressed | 4,582 B | 4,581 B | -1 B |
| Static SRAM (.data 0 + .bss) | 756 B | 756 B | 0 B |

All four linked images play the complete 32,000-sample model-exact PWM output,
with exact produced/played/timer-event/timer-tick counts, successful EOF,
empty terminal queue and zero decoder errors, observer errors or underruns.
The measured full-Flash saving is 100 B; the serialized saving is 99 B. Full
Flash includes linked code, tables, application/runtime and exact embedded
audio. The subtraction of only proven audio arrays is not an instruction-only
code-size measure.

The recipe is the current ATmega328P / AVR5 standalone release player,
16 MHz / 8 kHz, explicit ASM, queue 256 / prefill 192, v5-only, LPC segments 2,
unroll 1 / tuning 0, AVR-GCC 7.3.0 with `-Os -flto -mcall-prologues -mrelax`.
MCU, player, builder and external observer source match the integration
checkout at `0415d791`; decoder bytes match `5c7e0592`. Vendor metadata remains
in an unlinked sidecar. The observer is the established external simavr
observer; no diagnostic firmware cost is reused.

[Numeric measurements, full metrics and source/runtime pins](verification.json)
retain the exact compiler flags and complete per-image terminal/timing
counters. Source files, linked image bytes, embedded streams, saved PWM and
observer reports were rechecked after validation. Private recording/stream/
PCM/firmware fingerprints, paths, audio and generated images remain only in
ignored build storage.

One informal blind A/B comparison of this specific pair was recorded as
**near-equal sound**. A was the 1,701-byte stream; B was the 1,800-byte
original. Files retained the complete 32,000 samples, original level and the
same fixed PWM-to-PCM transfer. No loudness fitting was applied. The private
key, WAVs and detailed listening receipt stay in ignored build storage.
This single informal observation supports that description for this pair;
it does not establish audible improvement or a corpus-wide listening score.

A later source-versus-output inspection found that this particular input is
very quiet: its full-record RMS is about -61.49 dBFS. In the 20 lowest-energy
20-ms reference frames (10% of the recording, not certified silence), reference
RMS is -98.88 dBFS, versus -75.00 / -74.54 dBFS for A/B native PCM16. This
establishes an added low-level codec residual in those frames; it does not
identify every audible sound as noise. All corresponding fixed-PWM samples
are at neutral duty. Across the complete recording, only 378 / 400 of 32,000
A/B PWM samples are non-neutral, so 8-bit rounding strongly affects this quiet
example. No gain fitting, denoising, trimming or new encoding was performed.
The exact pre-LPX reference listening copy and numeric inspection receipt stay
in ignored storage. Near-equal A/B feedback remains scoped to this pair.

This is one held-out point and four complete simulator runs, with the separate
informal digital listening observation above. Physical-board/analog behavior
and universal bitrate-quality conclusions remain unverified. Existing
corpus-level results and later combined-search experiments have separate scope.
