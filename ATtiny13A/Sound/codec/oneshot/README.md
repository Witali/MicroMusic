# One-shot HQ4 build and candidate verification

`hq4.S` emits the complete speech phrase and then midpoint PWM (`128`) forever.
The numerical decoder's last-sample convention is preserved. The verifier checks
one complete phrase and two phrase lengths of silence in each of the JavaScript,
WASM, and unoptimized WASM AVR engines. The firmware uses no EEPROM; the erased
EEPROM supplied to the verifier is test scaffolding.

Build the retained Vinni release without changing its stream:

```sh
python tools/build-hq4-oneshot.py --clip vinni --output build/hq4-retained
```

The default build still rejects any numerical PCM mismatch with the retained
real-AVR recording. Its speech prefix remains byte-identical to the old HQ4.

An encoder can instead supply an explicit experimental stream:

```sh
python tools/build-hq4-oneshot.py --clip vinni \
  --stream build/hq4-search/vinni/speech.hq \
  --output build/hq4-search/vinni/avr
```

Use `--avr-bin PATH` and `--node PATH` when those executables are not on `PATH`.
The Python API is `build(clip, output, avr_bin=None, node='node', stream=None)`.
Keep candidate inputs and outputs under ignored `build/`; do not use a retained
release folder as the output directory.

Explicit candidate mode permits changed PCM, but requires the retained complete
phrase duration, complete HQ4 frames, legal duration/pitch fields, and an initial
full coefficient update. Supply no EOF byte: assembly appends it. The current
406-byte code region leaves at most 617 stream bytes plus one EOF byte in the
1024-byte image. An oversized candidate is rejected before assembly. A candidate
that does not pass assembly and all engine checks exits unsuccessfully.

`build.json` marks these inputs `experimental: true`, records both candidate and
retained stream hashes, and uses `input/speech.hq` as the stable candidate source
fingerprint. Input paths outside the checkout are reported as `external/NAME`,
without an absolute machine-specific path. `speech.hq`, the generated image,
`expected.raw`, and `actual.raw` remain together in the candidate output folder.
Candidate mode never updates the public catalog or retained release sources.

Admission tests: `python tools/test-hq4-oneshot.py`. A frozen Vinni stream passed
explicit external-input mode with 1024 Flash bytes, 22272 speech samples, and
44544 following samples all equal to `128` in all three engines. This qualifies
the build path; every changed candidate still requires its own verification.
# New recordings

For a newly encoded recording without a retained release directory, supply
`--stream FILE --samples N --clip recording-id`. `N` is the complete prepared
reference length (a positive multiple of 64), not a desired shortened length.
The builder checks exact equality before compilation, enforces 617 stream bytes,
and verifies the full phrase plus twice its length of midpoint silence. A new
recording report is marked `newRecording` and does not claim a frozen release
PCM hash. Omitting `--samples` preserves retained-clip behavior and guards.

