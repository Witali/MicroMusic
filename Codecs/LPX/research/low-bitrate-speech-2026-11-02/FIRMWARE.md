# Full ATmega328P firmware admission

The frozen round0 2 and 3 kbit/s candidates were checked as complete one-shot players
on ATmega328P / AVR5 at 16 MHz. Each contains the full 19,200-sample phrase,
plays at 8 kHz, and drives 62.5 kHz PWM on OC2B / PD3 / Arduino D3. These are
instruction-set and peripheral simulations, not physical-board measurements.

| Profile | Audio bytes | Actual bit/s, including header | Program Flash | Full Flash | Static SRAM | Peak stack |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sparse80, target 2 kbit/s | 578 | 1926.67 | 4880 B | 5458 B | 756 B | 60 B |
| v5/P4, target 3 kbit/s | 900 | 3000 | 4574 B | 5474 B | 756 B | 60 B |

Program Flash includes decoder, tables, player, and stream index; it excludes
only the exact, uniquely located embedded audio array. Full Flash is linked
`.text + .data`. Both images leave at least 1231 B between static SRAM and the
deepest observed stack. Queue/prefill are 256/192 samples. The sparse image
has 306 B more program Flash in this pair, so the 322 B audio saving reduces the complete short
image by only 16 B. This is a size observation, not a quality comparison or a
constant decoder-size formula for other streams.

Both images reproduce every independent PWM reference byte in simavr 1.6
with timers and interrupts active: 19,200 valid outputs, no underruns, and no
decoder error. The exact bundled browser ATmega328P core also reproduces all
19,200 PWM bytes with 19,200 interrupts and no lost timer event. Its output
intervals are 1995–2005 CPU cycles for sparse80 and 1995–2004 for v5/P4,
including interrupt latency around the 2000-cycle timer period. The numerical
receipts are in [firmware.json](firmware.json).

The sparse80 reference first expands the stored parameters and innovations
into ordinary v5/P6, then uses the existing independent v5 model. Neither the
reference expansion nor the diagnostic observer is linked into the player.
Browser playback duration uses the measured browser-core stop cycle, including
startup/prefill, rather than truncating the last samples at nominal duration.

Arithmetic is explicitly enabled with `LPX4_ENABLE_ASM=1`; real compiler AVR5
and hardware-MUL macros still gate its selection. The C fallback remains
selectable with `LPX4_ENABLE_ASM=0`, independently of Flash-memory access.
On the 895-byte provisional v5/P4 control, the compiled AVR C path produced
all 19,200 PWM bytes exactly but incurred 8493 underruns. It is a numerical
fallback, not the admitted 8 kHz playback profile. The new optional parser
does not affect the default-off v5 image: the full 5582 B player for the old
1008 B control is byte-identical to a build of the previous core.

## Reproduction

Use AVR-GCC 7.3.0 and the checked-in production player, with `-Os -flto
-mcall-prologues -mrelax`, `LPX4_AVR_DOT_UNROLL=1`,
`LPX4_FUNCTION_TUNING=0`, and explicit ASM enable. The sparse image also sets
`LPX4_ENABLE_SPARSE80=1`; ordinary v5 leaves that option off.

Build the current `Codecs/LPX/validation/atmega328p/sim_player.c` against a
matching simavr 1.6 SDK. Its observer ABI differs from `sim_profile.c`; do not
substitute an old profiling runner. The SDK used here needs `-lelf -lz -lzstd
-lpthread -lm` after `-l:libsimavr.so.2`.

The paired browser reproduction tool is preserved separately on local branch
`codex/arduino-speech-player` at `cafd572b`, with its pinned browser runtime in
parent `d73f9c8e`. Run the following command from that branch. The quality-only
branch retains the independent corpus admission tool documented below; it does
not adopt the browser UI or vendor runtime.

The paired tool builds both complete images, checks their exact
embedded audio regions and linked costs, runs the external simavr observer,
and then executes the exact browser core against the same independent PWM:

```text
python tools/build-arduino-speech.py --lpx2 <frozen-2k-stream.lpx> --lpx3 <frozen-3k-stream.lpx> --avr-bin <avr-toolchain-bin> --observer <current-sim_player> --simavr-lib <simavr-library-directory> --wsl Ubuntu --output build/reproduce-arduino-speech
```

Omit `--wsl` for a native host observer. Speex comparison builds are optional:
`--speex2 <raw-NB1> --speex8 <raw-NB3> --host-cc <host-C-compiler>` also rebuild
the untouched Xiph fixed-point narrowband oracle and admit both real players.
They do not reencode audio. All ELF files, logs, source snapshots, PCM, and
generated catalog/HEX review files remain under ignored `build/`. An explicit
`--export-web` copies only the admitted catalog and HEX into the local website
checkout; it does not publish, commit, or push anything.

Host emulator wall time is separate from simulated AVR timing. These firmware
checks do not guarantee real-time browser playback on every computer, nor do
two short streams establish timing for the entire speech corpus.

## Completed corpus admission

All 27 frozen round0 four-second corpus cases were subsequently admitted at both
caps: **54 complete production ASM images, 1,728,000 exact PWM samples,
zero underruns, zero decoder/observer errors**. The complete anonymous
per-image results are in [corpus-firmware.json](corpus-firmware.json).

| Target cap | Images | Audio bytes | Program Flash | Full Flash |
| --- | ---: | ---: | ---: | ---: |
| 2 kbit/s | 27 | 578–986 B | 4879–4880 B | 5458–5866 B |
| 3 kbit/s | 27 | 1414–1500 B | 4573–4574 B | 5988–6074 B |

Every image uses 756 B static SRAM, 51–60 B observed peak stack, and leaves
at least 1231 B between the static allocation and deepest stack. Minimum
queue before producer EOF is 192 samples in all 54 runs. Simavr timer output
intervals are 1997–2003 cycles. The one-byte program range is actual linked
layout; it was not replaced with a constant decoder-cost estimate. The stream
caps include complete headers and stored final packets. Lower rates in easy
cases are retained rather than padded to a constant stream size.

This corpus gate uses simavr with live interrupts; the additional exact
browser-core differential checks above cover the two short listening streams.
Neither establishes physical-board/analog behavior or the real-time speed of
the browser on arbitrary host computers.

These receipts cover round0 only. Changed streams selected by later quality
rounds require fresh complete-image admission before a firmware support claim.

The separate corpus gate accepts only finalized encoder jobs with `PASS`
completion receipts, checks each selected byte cap and native-reference
admission, and builds every complete 32,000-sample selection independently:

```text
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tools/validate_low_bitrate_firmware.py --corpus-ready-dir <completed-corpus-jobs> --output build/reproduce-lowrate-corpus-firmware --avr-bin <avr-toolchain-bin> --observer <current-sim_player> --lib <simavr-library-directory> --wsl Ubuntu --workers 2 --wait
```

`summary.json` records anonymous case ordinals, actual linked program/audio/full
Flash, SRAM/stack, exact PWM, queue minimum, and underruns. `complete` and
`expectedJobs` distinguish a partial run from full corpus admission. Private
per-image provenance remains in the same ignored output tree.
