# Adaptive target winners: complete-player admission

All three existing adaptive-search winners pass complete production playback
at normal and +100-cycle IRQ load. Against the accepted 1,702 B target stream,
full Flash grows by **8 B, 228 B and 358 B**. The decoder/player program does
not grow in this set. No fitting or quality selection occurs in this stage.

| Existing target stream | Actual stream, B | Full Flash normal / +100, B | Program excluding stream normal / +100, B | Full Flash growth, B |
| --- | ---: | --- | --- | ---: |
| accepted baseline | 1,702 | 6,276 / 6,284 | 4,574 / 4,582 | 0 |
| cap 1800, listening A | 1,710 | 6,284 / 6,292 | 4,574 / 4,582 | 8 |
| cap 1930 | 1,930 | 6,504 / 6,512 | 4,574 / 4,582 | 228 |
| cap 2060, listening B | 2,060 | 6,634 / 6,642 | 4,574 / 4,582 | 358 |

These are actual linked `.text + .data` sizes, including stream bytes, tables,
headers and layout. Program excluding embedded streams is measured separately;
its value must not be assumed for different assets or segment geometries.
Static `.data + .bss` is **756 B**, and observed minimum stack margin is
**1,231 B** in every row. All images fit the 32,768 B device Flash.

The three candidates are byte-distinct, V5/profile 4, one reset segment and
32,000 samples each. All eight rows pass complete physical PWM, EOF, produced/
played counts, timer ticks/events, empty final queue, decoder/observer status
and stack checks. There are zero underruns, output/timing failures or no-fit
rows. This covers 256,000 physical ticks, including 192,000 from six newly
built candidate images. One campaign attempt completed; no image attempt failed.

The baseline's two images are reused read only from earlier evidence after
strict current source/build recipe, compiler/header/library/harness, ordered
stream, ELF/binary/HEX, observer/runtime, physical PWM and report proof. They
are not counted as new simulations. Identical sizes or cap labels alone do not
permit reuse. All six candidate images are new in this campaign.

## Source, level and interpretation

The producer is frozen adaptive core `5a6cd1ab`; the consumer/native-library
epoch is `5b4800f7`, with MCU bytes unchanged from `5c7e0592`. Actual selected
streams, source target, producer binding, numerical reports and completion
markers are pinned before playback and rechecked afterward. They are existing
results, not refitted candidates. The observer/player imports, source inventory
and build/runtime dependencies are verified from the frozen consumer root.

The platform is ATmega328P/AVR5, 16 MHz, 8 kHz, queue 256/prefill 192 and the
existing explicit ASM recipe with AVR-GCC 7.3.0. The exact options and source
dependencies are retained in `source-runtime.json`. No ASM or arithmetic is
changed. Portable C stays selectable; this package makes no C real-time claim.
This is interrupt-active simavr evidence, not physical-board or analog-output
measurement. Observer instrumentation stays outside production firmware.

The source domain is the explicitly declared gain-64 target. Playback matches
each stream's own model, not the original recording or another candidate.
Current common and compact-only native PCM16/PWM match the independent model
before AVR admission and again in a read-only export check. The reference is
bound to the producer's exact prepared PCM; no output gain is fitted here.

The user's A/B comparison was **inconclusive**. In particular, the larger B
stream has no confirmed audible advantage from that comparison. All candidates
remain exploratory in this playback package; a larger stream is not adopted
because it passed simulation or has a lower encoder proxy score. SSE/STOI,
voice preservation and perceived rasp are assessed elsewhere. No original-
level quality or universal audibility claim follows from this target case.

## Evidence and reproduction

The campaign's timed admission region took 34.37 s. A subsequent read-only
artifact check reopens every image, source/build/runtime recipe and actual
expected output, rechecks native/model outputs and producer markers, then
exports anonymous numerical receipts. It performs no fit, AVR build or AVR
simulation. A local export-launch/path correction did not repeat the campaign.

`summary.json`, `rows.json` and `source-runtime.json` are exact anonymous
projections of the completed receipts. `artifact-check.json` records the final
read-only proof. Private source paths/identities, media/PCM/stream/firmware
fingerprints, bindings, generated images and logs remain in ignored build
storage. Public hashes identify source or generic tool/runtime dependencies.

`reproduction/adaptive_player.py` is the executed existing-asset admission
dispatcher. `player_evidence.py` and `admit.py` are unchanged generic helpers
from the earlier roughness-player package. Their exact source digests are in
`reproduction/sources.json`; earlier V1 sources and receipts remain untouched.

For a later authorized reproduction, supply the pinned Python 3.12 runtime,
frozen source, original prepared native libraries/player preparation and
immutable prior baseline evidence. Use fresh ignored output names:

```sh
python reproduction/adaptive_player.py \
  --source-root "$LPX_FROZEN_SOURCE_ROOT" --prepared "$LPX_PLAYER_PREPARATION" \
  --study "$LPX_COMPLETED_NATIVE_STUDY" --prior "$LPX_PRIOR_PLAYER_EVIDENCE" \
  --baseline "$LPX_TARGET1702" --producer "$LPX_COMPLETED_TARGET_STUDY" \
  --reference "$LPX_DECLARED_TARGET_REFERENCE" --input-gain 64 \
  --candidate "cap1800=$LPX_ADAPTIVE_TARGET1800" \
  --candidate "cap1930=$LPX_ADAPTIVE_TARGET1930" \
  --candidate "cap2060=$LPX_ADAPTIVE_TARGET2060" \
  --output build/adaptive-target-player-replay
```

Keep assertions enabled. No private audio, encoded stream or target firmware
is included in this package.
