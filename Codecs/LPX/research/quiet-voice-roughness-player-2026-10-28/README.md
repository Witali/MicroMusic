# Exploratory roughness candidates: player admission

All three existing candidates pass actual production playback at normal and
+100-cycle IRQ load. Relative to the exact 1,702 B target baseline, complete
Flash grows by **2 B, 210 B and 228 B**. This is playback/size evidence only:
the candidates remain exploratory and unadopted, with no new fits or quality
promotion. The declared input gain is 64 for this target-domain comparison.

The assets' 1800/1930 labels identify search budgets, not serialized lengths.
Actual byte counts, headers, tables and linked layout are charged below:

| Existing variant | Actual stream, B | Full Flash normal / +100, B | Program excluding stream normal / +100, B | Full Flash growth, B |
| --- | ---: | --- | --- | ---: |
| target baseline | 1,702 | 6,276 / 6,284 | 4,574 / 4,582 | 0 |
| LPC, cap 1800 | 1,705 | 6,278 / 6,286 | 4,573 / 4,581 | 2 |
| extras, cap 1930 | 1,913 | 6,486 / 6,494 | 4,573 / 4,581 | 210 |
| extras then LPC, cap 1930 | 1,930 | 6,504 / 6,512 | 4,574 / 4,582 | 228 |

The -1 B program differences are linked-layout effects; decoder/player code
is unchanged. Full Flash is actual linked `.text + .data`, including all
embedded stream bytes. Static `.data + .bss` is **756 B** and observed minimum
stack margin is **1,231 B** throughout. Every image fits within 32,768 B Flash.

Each variant is V5/profile 4, one reset segment and 32,000 samples. Current
common and compact-only native PCM16/PWM match its own model before AVR
validation. All 32,000 physical output samples, produced/played counts,
EOF, ticks/events, empty queue termination, error status and stack checks pass
for every row with zero underruns or observer/decoder errors. There are no
hidden failed or size-limit rows. Across the eight rows, 256,000 physical ticks
are checked, including 192,000 from six new candidate images.

The two baseline images are reused read only from the earlier admitted V1
union after exact current source/build recipe, compiler/header/library/harness,
ordered data, ELF/binary/HEX, observer/runtime, expected PWM and report proof.
They are counted as reuse, not new simulations. Later controller winners may
reuse this evidence only after the same exact-byte/source/build proof; a shared
filename, budget or byte count is insufficient.

## Source and interpretation

The consumer source epoch remains frozen `5b4800f7`, with MCU bytes unchanged
from `5c7e0592`. Candidate searches happened elsewhere before this admission;
their encoder changes are not executed here. The player/observer, model and
native imports all come from the frozen consumer root. V1 core, tests, study
protocol, assets and research labels are not edited.

The target is ATmega328P/AVR5, 16 MHz, 8 kHz, queue 256 and prefill 192, using
the existing explicit ASM size recipe with AVR-GCC 7.3.0. Vendor hardware access
stays separate from backend selection. Portable C is retained; no C real-time
claim or new ASM is introduced. Observer metadata remains outside production.
This is simavr evidence, not a physical-board or analog-audio measurement.

Every waveform matches its own model; the candidate waveforms are not claimed
to be identical to the baseline or original recording. No SSE/STOI/voice or
perceived-roughness gate is measured or promoted in this stage. The declared
gain64 target domain is explicit; this is not an original-level or equal-
loudness quality claim. The user's operational amplification choice is separate
from whether an exploratory LPC/excitation candidate is adopted.

The eight-row run took 25.55 s. A read-only export rechecks current source and
asset bytes, actual linked image/binary and expected-output fingerprints,
runtime/flags, full PWM/EOF/ticks/queue/stack and exact numeric projections.
It builds no additional image and performs no fit or playback measurement.

## Evidence and reproduction

`summary.json`, `rows.json` and `source-runtime.json` are exact anonymous
projections of the completed receipts. `artifact-check.json` records the final
read-only check. Actual private assets, paths, per-recording/PCM/firmware
fingerprints, generated headers, images and logs stay in ignored build storage.
Public hashes identify source or generic tool/runtime dependencies only.

`reproduction/roughness_player.py` consumes already frozen existing assets.
`player_evidence.py` extracts the reusable exact-source/build/data/runtime image
proof from the earlier V1 helper; frozen V1 source/receipts remain unchanged.
`admit.py` provides current-root import/output guards and preparation. Exact
executed source hashes are retained in `reproduction/sources.json`. Failures or
actual linked Flash overflow stay visible; playback never selects a quality
winner or activates an encoder policy.

For a later authorized reproduction, supply Python 3.12, the pinned source and
runtime, existing prepared native libraries, a source-bound player preparation,
and the prior immutable baseline evidence. Use a fresh ignored output directory:

```sh
python Codecs/LPX/research/quiet-voice-roughness-player-2026-10-28/reproduction/roughness_player.py \
  --source-root "$LPX_FROZEN_SOURCE_ROOT" --prepared "$LPX_PLAYER_PREPARATION" \
  --study "$LPX_COMPLETED_NATIVE_STUDY" --prior "$LPX_PRIOR_PLAYER_EVIDENCE" \
  --baseline "$LPX_TARGET1702" --input-gain 64 \
  --candidate "lpc-cap1800=$LPX_LPC_CANDIDATE" \
  --candidate "extras-cap1930=$LPX_EXTRAS_CANDIDATE" \
  --candidate "extras-then-lpc-cap1930=$LPX_COMBINED_CANDIDATE" \
  --output build/roughness-player-replay
```

Keep assertions enabled; do not use Python optimization flags. No private
asset or target firmware is included in this package.
