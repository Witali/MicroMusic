# Final integration checks

The production algorithm is frozen in5abd9f57.7ea4e1aa adds actual-GPU and
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
