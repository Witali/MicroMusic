# HQ4: refinement without replacing the accepted decoder

The rejected voice-priority prototype motivates starting again from the retained
HQ4 stream. `tools/refine-hq4-speech.py` keeps the original 406-byte, signed
eight-bit lattice and performs all analysis on the PC. No FFT, new coefficients
or floating-point code is added to the microcontroller.

## Search and acceptance

The existing HQ4-T search already supports correlated parameter edits, frame
boundary changes, split/merge and voiced/unvoiced alternatives. This search reuses
those proposals with the original HQ4 arithmetic and its 617-byte stream budget.
It also tests octave alternatives and adjacent-frame periods as candidates;
neither an estimated F0 nor an attack detector forbids a synthesis alternative.

The score combines 70% of the existing multi-resolution STFT objective, 20%
of the new one-third-octave band-envelope/shape objective and 10% of the
persistence-weighted spectral error. These comparisons use
the same 70 Hz highpass and global RMS match. Band envelopes retain time context;
band shape measures how energy is distributed between frequency regions. The
persistent-ridge analysis additionally identifies lasting peaks and their
deficit/excess. Positive weights softly emphasize those regions during search,
without directly adding or removing sinusoids in the signal.

The exported elite must preserve **both STOI and eSTOI of the frozen HQ4 stream**,
the original multi-resolution spectral loss and its log-error ceiling. Peak
signed PCM must be at most 115; steps of 48 or more are rejected. The full
recording length is preserved; decoder + stream + EOF must fit 1024 bytes.
The initial stream remains available if no acceptable improvement is found.
Exploratory states may temporarily violate quality floors, but are never
exported. A lower objective is not a claim of better subjective quality.

The current tool refines a supplied stream; it is not a general initial encoder
for arbitrary new speech. It intentionally does not replace a public example.
An explicit `--input-stream` must already satisfy the frozen HQ4 floors and
ceilings. Its quality cannot weaken those limits. The listening comparison
uses that input as the "before" sound; the report records both frozen control
and input metrics separately.

## Reproduce and resume

```powershell
python tools/refine-hq4-speech.py --clip vinni --reference C:/Work/MicroMusic/build/hq4-preview/vinni/original.wav --output build/hq4-refinement/vinni --proposals 6000 --seed 23101
python tools/refine-hq4-speech.py --clip vinni --reference C:/Work/MicroMusic/build/hq4-preview/vinni/original.wav --output build/hq4-refinement/vinni --proposals 12000 --seed 23101 --resume build/hq4-refinement/vinni/checkpoint.json
python tools/build-hq4-oneshot.py --clip vinni --stream build/hq4-refinement/vinni/speech.hq --output build/hq4-refinement/vinni/avr --avr-bin C:/Work/MicroMusic/build/toolchains/avr-7.3.0/bin --node C:/Work/MicroMusic/build/toolchains/node-22.22.3/node.exe
```

Keep sources unchanged when resuming. Checkpoints retain exact streams, metrics
and random-generator state; source/input hashes and recomputed metrics reject
incompatible resumes. Proposal count includes pre-synthesis budget rejections.
The eSTOI wrapper isolates pystoi's epsilon-scale random normalization with a
fixed NumPy RNG seed and restores the caller's RNG state after each evaluation.
Search schedule parameters must be identical; stopping and resuming reproduce
an uninterrupted run. This is best-effort optimization, not a global minimum.

Generated files remain in ignored `build/`: `speech.hq`, `expected.raw`, exact
`decoded.wav`, checkpoints and reports. `original-matched.wav`,
`before-matched.wav`, `after-matched.wav` use the same highpass, RMS and common
peak scale. `comparison.wav` plays original → baseline → original → candidate,
with 300 ms gaps. Metrics are calculated before listening normalization.

Final approval requires real HEX verification of the entire phrase, timing,
stack and subsequent midpoint silence in all three emulators. Physical hardware
and subjective listening remain separate checks. Mixed excitation or an extra
frequency residual is a later experiment with its own byte/cycle budget.

```powershell
python tools/test-hq4-speech-search.py
python tools/test-speech-spectrum.py
python tools/test-hq4-oneshot.py
```
