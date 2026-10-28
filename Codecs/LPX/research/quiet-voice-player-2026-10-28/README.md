# Quiet-voice research target: production-player admission

One frozen research pair passes all four actual production-player images at
normal and +100-cycle IRQ load. The candidate saves **98 B of complete linked
Flash** at both loads. Decoder/player source and program size are unchanged.
This report validates playback of that pair, not an encoder-quality decision.

The handoff explicitly uses `reference_domain: auto-declared-target`,
`old_playback_gain: 1`, `new_input_gain: 64`, and `quality_adopted: false`.
The changed input/playback-level distinction remains part of the experiment.
Optional auto gain is **research only**, not an active default. These results
make no original-level quality, equal-loudness, timbre or audibility claim.
Each image matches its **own** current-model output; original and candidate
waveforms are not claimed to be identical to each other.

## Measured complete images

The pair has 32,000 samples, profile 4 and one reset segment. Both streams remain
V5; no decoder format or arithmetic change was made. The source epoch is
`5b4800f7`, with MCU decoder bytes unchanged from `5c7e0592`. All LPX imports,
builders, native/model validation and source/runtime fingerprints came from
that current quiet-voice epoch, independently of older experimental worktrees.

| Role | IRQ load, extra cycles | Stored stream, B | Full Flash, B | Program excluding stream, B | Static SRAM, B |
| --- | ---: | ---: | ---: | ---: | ---: |
| original control | 0 | 1,800 | 6,374 | 4,574 | 756 |
| candidate research target | 0 | 1,702 | 6,276 | 4,574 | 756 |
| original control | 100 | 1,800 | 6,382 | 4,582 | 756 |
| candidate research target | 100 | 1,702 | 6,284 | 4,582 | 756 |

Full Flash is actual linked `.text + .data`, including code, tables, headers,
exact embedded audio and linker layout. Program Flash subtracts the stored
stream bytes; it changes by 0 B. Static `.data + .bss` is 756 B and the observed
minimum stack margin is 1,231 B in every image. All images fit 32,768 B Flash.
There are no dropped, no-fit or failed-timing rows in this four-image handoff.

Each image produced and played exactly 32,000 samples with matching physical
PWM, 32,000 timer ticks/events, successful EOF, empty queue termination and zero
decoder errors, observer errors or underruns. Common and compact-only native
C PCM16/PWM match the current independent model before AVR playback. Across
the four images, all **128,000 physical output ticks** are checked.

The player uses ATmega328P/AVR5 at 16 MHz, 8 kHz audio, queue 256 and prefill 192.
AVR-GCC 7.3.0 uses the retained size recipe (`-Os`, LTO, call prologues, relax,
unroll 1 and function tuning 0). Existing vendor-based memory access and explicit
architecture/ASM gating are preserved; no ASM was added. Portable C remains
selectable, but C real-time playback was not tested or admitted here. The
observer and its vendor-derived metadata stay outside the production ELF.
These are simulator results, not physical board measurements.

The measurement took 19.41 s. A read-only artifact recheck verifies the current
source inventory, exact dispatcher bytes, saved image/binary fingerprints,
complete retained PWM, timer/EOF/queue/stack status and paired Flash arithmetic.
That export step performs no new target build or playback measurement.

## Evidence and parameterized protocol

`summary.json`, `rows.json` and `source-runtime.json` are exact copies of the
completed anonymous numeric/source receipts. `compiler-options.json` records
the actual flags at both IRQ loads; `artifact-check.json` states the narrower
read-only recheck scope. Per-recording identities, input paths, media/PCM/ELF
fingerprints, firmware, generated headers and logs stay in ignored private
receipts. Shared source, compiler, vendor-header and simulator/runtime hashes
are retained.

`protocol/admit.py` prepares the observer and pins the selected source epoch.
`protocol/target.py` accepts a frozen private handoff only after preparation.
Every LPX module origin must be under `--source-root`; source HEAD may move for
documentation while the captured source inventory must remain unchanged.
The handoff binds the exact preparation receipt and ordered complete streams.

Each private pair carries an id, `original` and `candidate` chain entries,
explicit reference domain, old playback gain, new input gain, quality-adoption
flag and scope. Chain entries carry samples, profile, complete `file_bytes`,
and segments with path, stream fingerprint, byte/sample counts, start and index.
Optional whole-chain PCM/PWM fingerprints are checked when supplied. The
dispatcher checks actual full serialized bytes; it does not allocate budgets,
re-encode, choose candidates, normalize level or promote raw quality results.

All actual failures remain rows. Data already larger than 32 KiB and actual
linked text overflow have separate no-fit statuses. Timing/output failures are
retained with the complete observer report. An input/source/runtime mismatch
stops validation instead of accepting stale evidence. New candidate choices
require a new frozen handoff and explicit execution authorization.

For a later authorized reproduction, use Python 3.12 and the dependencies in
`source-runtime.json`. Run from the repository root with local paths supplied
through environment variables and keep outputs in a fresh ignored directory:

```sh
python Codecs/LPX/research/quiet-voice-player-2026-10-28/protocol/admit.py prepare \
  --source-root "$LPX_SOURCE_ROOT" --output build/quiet-voice-replay \
  --avr-bin "$LPX_AVR_BIN" --include "$LPX_SIMAVR_INCLUDE" \
  --lib "$LPX_SIMAVR_LIB" --wsl "$LPX_WSL"
python Codecs/LPX/research/quiet-voice-player-2026-10-28/protocol/target.py \
  --source-root "$LPX_SOURCE_ROOT" --handoff "$LPX_FROZEN_HANDOFF" \
  --prepared build/quiet-voice-replay/preparation-private.json \
  --output build/quiet-voice-replay/targets
```

The handoff must refer to that preparation's exact private hash. No private
handoff is included. The source copies retain their measured bytes; this report
does not claim exhaustive generic-dispatcher input coverage, corpus-wide
playback coverage, music performance or any default change.
