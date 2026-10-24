# Bounded mixed-excitation experiment on original HQ4

The proposed next decoder experiment was to mix a small amount of noise into
periodic excitation for rough voices. The PC prototype in `codec/hq4_mixed.py`
duplicates the original exact signed eight-bit HQ4 lattice and adds quantized
noise **before** that lattice. This is not the previous period-wave model and
it does not add fixed-frequency oscillators or change any public firmware.

Each original frame has a two-bit code:

| Code | Added noise magnitude |
| ---: | --- |
| 0 | Off |
| 1 | Original frame gain shifted right by two |
| 2 | Original frame gain shifted right by one |
| 3 | Original frame gain |

For voiced frames only, the existing 8-bit `0xa7`/`0xb8` LFSR supplies the
noise sign. The original pulse sequence is retained; the added excitation
and lattice use the same intentional eight-bit wrapping arithmetic as HQ4.
There is no floating-point synthesis, reference lookup or extra source audio
inside decoding.

The LFSR advances during voiced playback only when the added noise magnitude
is nonzero. Therefore all-zero maps, a disabled mix stage, and zero-amplitude
flags preserve the original decoder output and future unvoiced LFSR state
exactly. A nonzero voiced mix intentionally changes later unvoiced noise
phase because it shares that LFSR; this is a known confound when interpreting
any improvement as a change specifically to vocal roughness.

## Vinni result: reject the extension for now

The [retained report](vinni/quality.json) uses the frozen
`codec/release/vinni/speech.hq` and the canonical, hash-checked full
22,272-sample original at 7.5 kHz. All original frame coefficients, pitch,
gain and durations are fixed. Only the two-bit mix map is searched.

The search made 2,000 bounded proposals with seed 23102. It tested all 257
distinct nonzero single-frame/level starting maps, then tried local joint
changes with a deterministic exploratory chain. Duplicate maps and zero-noise
equivalents were avoided. It evaluated 920 unique maps; 261 violated the
existing peak or discontinuity constraints. The baseline all-zero map remained
available throughout.

| Metric | Original HQ4 / selected output | Lowest-loss unconstrained mix |
| --- | ---: | ---: |
| STOI | 0.859602 | 0.853268 |
| eSTOI | 0.690986 | 0.681372 |
| Log spectral error | 0.812884 | 0.811064 |
| Combined spectral loss | 0.823229 | 0.821736 |
| Band envelope loss | 0.393252 | 0.393012 |
| Band shape loss | 1.063867 | 1.064978 |
| Enabled mix frames | 0 | 3 |

The unconstrained mix slightly reduces the spectral error but worsens both
intelligibility metrics and one band metric. It is rejected. **No candidate
satisfying both baseline intelligibility floors and both spectral ceilings
improved the search objective.** The selected output therefore remains
bit-identical to original HQ4. There is no audible improvement claim and no
reason to promote this decoder extension to the public player.

The objective combines 70% existing multiscale spectral loss, 20% temporal/
spectral band loss, and 10% persistent-ridge spectral loss. Independent export
guards require STOI and eSTOI no lower than frozen HQ4 and both multiscale
spectral metrics no higher. Peak signed amplitude must remain at most 115;
sample steps of 48 or more are rejected. Both inputs undergo the existing
common highpass/global RMS matching for spectral comparison. Full-record
STOI/eSTOI remain unfiltered, deterministic PC measurements; neither they nor
the spectral metrics substitute for listening.

This is bounded negative evidence for these four excitation levels on fixed
HQ4 parameters. It does not disprove mixed excitation in general. A useful
later experiment would jointly refit the lattice coefficients and excitation,
or compare an independent voiced-noise state to remove the phase confound.
The encoder-only search on the unchanged decoder should be exhausted first.

## Storage and implementation limits

Vinni has 140 frames, so its two-bit map needs **35 bytes**, which could fit
in the ATtiny13A's 64-byte EEPROM. This only establishes data capacity.
The original 406-byte decoder and 617-byte stream already fill the 1024-byte
Flash image including the end marker. A coarse engineering allowance of
40–80 extra Flash bytes would be needed for an EEPROM map reader, per-frame
level selection and voiced LFSR/addition path. That range is **an estimate**,
with no register allocation, code-sharing, assembler or cycle audit. The
extension is not claimed to fit Flash, SRAM or timing. A new assembly
implementation and actual emulator verification would be required before
making any such claim.

## Reproduction

With the existing codec Python dependencies, from the repository root:

```powershell
python tools/test-hq4-mixed.py
python tools/probe-hq4-mixed.py --clip vinni --proposals 2000 --seed 23102 --output build/hq4-mixed/vinni
```

The generated original/baseline/mixed WAVs and A/B comparison remain in
ignored `build/`; the chosen mixed WAV equals the baseline. The report retains
the decoder/analysis source hashes, canonical original hash, unchanged input
stream hash, selected and rejected mix codes, selected PCM/map hashes and
runtime versions. `--input-stream` can test a previously accepted HQ4 stream;
the export guards still refer to the frozen release.

Five tests cover all-zero bit-exact identity for all three frozen phrases in
both phase modes, disabled/zero-amplitude state preservation, deterministic
nonzero signed synthesis and duration, two-bit packing/padding, and malformed
frame/map rejection. No generated WAV or temporary binary is tracked.
