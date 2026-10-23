# Repository rules

- Never store, stage, commit, or push MIDI source files (`.mid`, `.midi`, or `.smf`) in this repository.
- Read imported MIDI from an external location and convert it to structured musical-event JSON with `tools/midi-events.py`. Preserve tracks, event order, ticks, Note On/Off, programs, tempo changes, controllers, metadata, and source hashes.
- Keep temporary MIDI test fixtures outside the repository and remove them after use. Generated firmware and retained source descriptions must use JSON, not a copied MIDI binary.
- Commit each logically complete change separately and stage only files belonging to that change.
