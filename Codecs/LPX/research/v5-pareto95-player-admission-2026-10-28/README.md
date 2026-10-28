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

This is one held-out point and four complete simulator runs. It is not a
physical-board, analog-output, blind-listening or universal bitrate-quality
claim. Existing corpus-level results and later combined-search experiments
have separate scope and evidence.
