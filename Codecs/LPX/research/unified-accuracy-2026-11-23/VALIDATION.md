# Final integration checks

The allocation policy is frozen in5abd9f57.7ea4e1aa adds actual-GPU and
four-level Long checks;4037539b adds bounded source input/UI. Merge76585983
retains released14e6 reports byte-for-byte and both AVR cookbook observations;
its production encoder/decoder sources and assets are unchanged from the
tested accuracy/input commits. No new decoder wire syntax or Python runtime.

- Broad LPX Node run:138 tests,134 passes,2 optional legacy CUDA skips,2
  reference-setup failures. One helper was given a nonexistent WSL distro and
  one numerical seam an incorrect local path. Corrected independent
  bitrate/actual-rate quality re-run:9/9 pass. No functional failure remains.
- Final direct-accuracy checks:6/6 pass, including all12 preset/rate fast
  combinations on native CPU, actual CUDA, scalar and SIMD; full P8 CPU/CUDA
  equality; silence, arbitrary decoder reads/EOF/reuse; all four continuous
  Long presets; exact legacy P4/P6 fast-window compatibility.
- Full public paired output:6 native CPU files and2 changed-pair CUDA files
  agree byte-for-byte with scalar/SIMD outputs. Whole-output measurements and
  negative tradeoffs are retained in the paired report.
- Final source unit/native checks:12/12 pass. Demux limits/corruption, actual
  decoder queue/lifetime/flush protocol, C++ native/WASM FIR, arbitrary packet
  boundaries, fixed memory, frequency response, local quota/cleanup/recovery.
- Final WebUI/legacy-preset tests:6/6 pass. File objects reach the Worker
  without whole AudioBuffer decoding for supported source formats; all rates,
  explicit backend/search choices, normalization, cancellation and old strict
  APIs remain covered.
- In-app browser: changing synthetic MP3 with/without Xing, M4A, ADTS and WAV
  decoder comparisons pass; normalized P8 and ordinary P3/16k conversions pass;
  a long input yields one verified Long output; cancellation leaves zero
  app-owned temporary files. Private filenames/media/per-recording results
  remain excluded. Browser source-rate decoding and FIR response are separate
  checks, as described in AUDIO_INPUT.md.

The broad run's optional legacy GPU tests are not counted as new-policy GPU
proof. Actual new-policy hardware checks above provide that evidence. The
archived AVR fast-pair report is scoped separately and establishes no support
claim for the final policy or arbitrary streams.

Staged audits inspected41 accuracy files and25 input/UI files with zero
privacy findings. The resolved integration audit inspected all newly outgoing
history/objects with zero findings. Only the exact main ref is intended for
push; private corpus, listening artifacts, local logs, stash and task refs are
excluded. ChatGPT Sites publication/update is not part of this change.

## First-enhancement accounting correction

A final allocator review found that a zero-extra seed has no per-group
presence bits in its packed representation. The first correction must pay for
all actual group flags as well as its ten-bit symbol. The previous final-size
guard kept the cap safe but could discard the entire proposal instead of a
useful subset. First activation is now exact-packed once; subsequent symbols
reserve their ten bits conservatively. Activity is amplitude!=0, matching the
packet writer, including inactive symbols with nonnegative positions. If the
first symbol cannot fit, all other new symbols have identical syntax cost;
allocation stops instead of repeatedly packing the entire stream.

The new tight-budget regression requires one useful fitting correction and
strict decoded-error reduction, retains the seed when no correction fits,
tests both inactive position representations, and validates the complete EOF.
It passes portable native C++ and repeated scalar/SIMD WASM calls. Compiling
the previous accounting against the same regression fails the useful-subset
check, demonstrating the failure it detects. Final accuracy/native/CUDA/Long
suite including this regression:7/7 pass. The policy and objective equations
are unchanged. All six frozen public P6/P8 streams and all six fixed known
wideband streams remain byte-identical after the correction. Public output
checks total20 across scalar/SIMD/native CPU and the changed CUDA pair; the
private recheck emits only the aggregate6/6 equality result. Existing paired
metrics and their negative tradeoffs therefore remain unchanged.

Build the isolated regression with `node web-player/scripts/build-lpx-accuracy-tests.mjs --emsdk <sdk>`
and set `LPX_ACCURACY_ALLOCATION_SCALAR` and `LPX_ACCURACY_ALLOCATION_SIMD`
to its two generated WASM files when running `lpx-accuracy.test.mjs`.
Test seams add no production WASM export or wire field.
