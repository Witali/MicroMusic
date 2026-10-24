# Measured harmonic tolerance versus actual Q3 stream size

These bounded experiments demonstrate an actual compression control. The
encoder shares/refits coefficient groups and merges legal adjacent frames,
then measures the exact integer decoded result. Every accepted operation
reduces the serialized speech stream. A looser sweep level retains the
previous level's model, so bytes cannot increase. No waveform is shortened.

The frozen inputs are the Q3/T1 models in `research/hq4-q3/public-vinni/`
(22,272 samples, 602 speech bytes) and `research/hq4-q3/tail-voice/` (12,800
voice samples, 430 speech bytes). They are the controls for these rate studies,
not a replacement for the later highest-quality harmonic-refined auditions.

## Absolute-original p95 sweeps

The default p95 statistic is weighted by **matched original-partial power**.
It is not a maximum error bound for every instantaneous partial. The
reference's strongest ten partials are selected automatically at each time;
matching and reference track IDs remain fixed by their independent acoustic
rules. Missing/extra energy, match coverage and continuity break rate may not
worsen relative to the frozen input model at any sweep level.

| Recording | Frequency cap, cents | Amplitude cap, dB | Speech bytes | Measured p95 cents / dB | STOI | eSTOI |
|---|---:|---:|---:|---:|---:|---:|
| Vinni input | — | — | 602 | 111.28 / 17.59 | .83840 | .64461 |
| Vinni | 125 | 20 | 468 | 110.09 / 13.34 | .79911 | .54837 |
| Vinni | 175 | 22 | 340 | 158.84 / 16.28 | .71076 | .43307 |
| Vinni | 250 | 26 | 327 | 124.56 / 14.30 | .69700 | .42914 |
| Final voice input | — | — | 430 | 68.07 / 13.88 | .83667 | .55057 |
| Final voice | 75 | 15 | 329 | 73.26 / 14.81 | .79656 | .47040 |
| Final voice | 100 | 16 | 237 | 80.24 / 13.59 | .71324 | .33662 |
| Final voice | 150 | 18 | 219 | 86.65 / 17.32 | .67272 | .28267 |

Each absolute sweep used 300 candidate evaluations per level, two optional
joint coefficient repairs per byte-saving operation and seed 23191. The caps
are allowances, not targets that the search must fill. Individual errors can
improve again at a looser level while bytes decrease.

**The table shows a size/quality tradeoff, not a speech-quality upgrade.**
Harmonic p95 caps alone permit a substantial STOI/eSTOI decline, even while
coverage and excess-energy limits hold. The tool therefore also exposes
optional `--minimum-stoi` or `--maximum-stoi-drop` guards. Those options were
unset in these explicit tolerance-versus-size demonstrations. Selected
highest-quality listening firmware remains separate.

## Actual and computed firmware sizes

For Vinni, the three complete standalone Flash sizes are 890, 762 and 748
bytes: 420 bytes of Q3/T1 code, speech, one EOF byte and word alignment. The
smallest **748-byte image is actually verified** with reference, WASM and
unoptimized WASM AVR engines for all 66,816 samples: 22,272 voice samples plus
twice that duration of midpoint silence. It uses no EEPROM, loses no events
or samples, and has at least 440 CPU cycles of timing slack at 9.6 MHz.

For the final voice, the complete standalone sizes are 750, 658 and 640 bytes.
The smallest **640-byte voice image is actually verified** for 38,400 samples
with the same three engines: 12,800 voice samples plus twice that duration of
silence. It uses no EEPROM and has at least 482 cycles of slack. Both images
retain 30-byte maximum SRAM spans including stack use and have zero PCM
mismatches, internal arithmetic wraps or large adjacent sample steps.

With the previously qualified 576-byte bell/Q3-T1 core and 15-byte bell
descriptor, the corresponding complete bell-plus-voice Flash sizes would be
**922, 830 and 812 bytes**, plus 64 EEPROM bytes. Those three combined images
are **computed**, not assembled or qualified here. A new composite build must
balance the bell against its chosen voice and pass its own quality gates.

## Relative-error and strict-bound controls

The separate `relative/` studies used 400 evaluations at each additional
p95-error level, 0 cents/0 dB, +25 cents/+1 dB and +75 cents/+2 dB. The baseline
always remains the original 602/430-byte input, not the preceding looser
level. Vinni's stream decreases 602 → 470 → 360 → 341 bytes; the final voice
decreases 430 → 400 → 241 → 227. These are explicitly additional-error studies,
not absolute-original caps. Every level also reports STOI/eSTOI and full
spectrogram components so the quality cost remains visible.

At strict **absolute** p95 caps of 50 cents and 3 dB, neither frozen input is
feasible. A bounded 128-evaluation search found no smaller feasible candidate.
The original 602/430-byte streams are retained and clearly flagged
`infeasible-tracking-bounds`; they are not presented as meeting those caps.
This result is limited to the bounded search, not a theoretical limit.

## Provenance and reproduction

The source interface gained `max` and optional STOI guards after these p95,
no-STOI-floor searches were captured. Active search semantics for these runs
did not change. Every one of the 14 exported models was independently decoded
and rescored with the final frozen source in commit `5db48d4`, with full
duration, packing, wrap, PWM, track caps, STOI/eSTOI, complete spectrogram and
source-hash checks. Reports preserve both capture fingerprints and the final
evaluation fingerprints, and explicitly record this timing. No extra search
was used for that validation.

Per-level compressed models, streams and measured results are retained here.
The two smallest absolute levels also retain complete actual AVR build
reports. Original MP3s, WAVs, firmware binaries, verifier traces and complete
per-operation tracking trajectories remain outside the retained source tree
or under ignored `build/`. The final-voice original/excerpt provenance is
described in `research/natural-timbre/README.md`.

```sh
python tools/test-q3-track-rate.py
python tools/compress-hq4-q3-tracks.py \
  --reference web-player/audio/originals/vinni.wav \
  --model ATtiny13A/Sound/research/hq4-q3/public-vinni/model.json \
  --output build/q3-track-rate-absolute/vinni \
  --sweep 125:20,175:22,250:26 --max-evaluations 300
```

For the final voice, use its complete prepared voice reference and retained
Q3/T1 model with `--sweep 75:15,100:16,150:18`. For relative sweeps add
`--relative-to-baseline --sweep 0:0,25:1,75:2 --max-evaluations 400`.
For a hard cap on every matched partial use `--error-statistic max`; this
computes maxima from the matched trajectories without changing matching or
silently replacing a maximum with p95. Strict maximum bounds may likewise be
infeasible. See `codec/Q3_TRACK_RATE.md` for CLI details and optional standalone
three-engine qualification.
