# Repository rules

- Never store, stage, commit, or push MIDI source files (`.mid`, `.midi`, or `.smf`) in this repository.
- Read imported MIDI from an external location and convert it to structured musical-event JSON with `tools/midi-events.py`. Preserve tracks, event order, ticks, Note On/Off, programs, tempo changes, controllers, metadata, and source hashes.
- Keep temporary MIDI test fixtures outside the repository and remove them after use. Generated firmware and retained source descriptions must use JSON, not a copied MIDI binary.
- Commit each logically complete change separately and stage only files belonging to that change.
- Prefer official device definition files, register headers, and device family packs from the microcontroller manufacturer's official website whenever they are available. Reuse those definitions instead of manually duplicating register addresses. Pin the source URL and version, retain licensing and provenance, and keep project-specific adaptations separate from the original vendor files.

## Architecture optimization cookbooks

- While working on any processor architecture, preserve useful newly discovered references, reusable code examples and original optimization techniques in that architecture's folder: `docs/<architecture>-asm-cookbook/` (for example, `docs/avr-asm-cookbook/`). Create folders as needed and use consistent architecture names.
- Keep a compact `README.md` explaining each technique. Store reusable source examples in `examples/` when a separate file is useful; small snippets may stay inline in the README. Update existing entries rather than duplicating them.
- Specify the applicable CPU/core, ISA extensions, ABI, toolchain and correctness constraints. Explain whether the benefit concerns speed, code size or working memory. Link external sources and preserve provenance and license notices for adapted code.
- Clearly distinguish untested ideas, assembled examples and measured improvements. For measured changes, record the workload, compiler/options, before/after results and validation; avoid claiming portability or speedups beyond that evidence.
- For real-time audio optimizations, verify output timing and buffer underruns with interrupts active before claiming the profile is supported.
- Every handwritten assembly optimization must retain an equivalent, explicitly selectable C fallback, including when building for the optimized architecture itself. Keep hardware memory access separate from arithmetic backend selection, and verify the C and optimized paths against the same reference output. Preserve a portable library interface for other processor architectures.
- Select assembly only when architecture defines identify a supported target and a separate explicit assembly-enable define is set. Default to C when assembly is not enabled or no matching architecture/backend exists. Accept architecture settings from platform/manufacturer headers and retain the compiler's real CPU/memory-model macros.
