# Fit speech parameters and spectral noise before changing the Tiny decoder

Measured workload: the complete public bread phrase, 2.4 seconds; ATtiny13A
AVR25 at 9.6 MHz, AVR-GCC 7.3 / GNU assembler, existing bare-metal one-shot
Tiny decoder. Its register ownership and interface are unchanged. No new
handwritten assembly, arithmetic backend or callable C ABI is introduced.
The integer Python reference and three AVR execution configurations remain
unchanged.

An initial assembled candidate measured 1074 bytes. Bounded dictionary search
(1/2/4/8 periods), regional parameter holding and exact integer refinement found
a 1022-byte complete Flash image plus 64 bytes read-only EEPROM. The alternate
pitch analysis fit in 1024 bytes but had lower STOI (0.6741 versus 0.7243).
The unconstrained quality variants exceeded Flash (1092/1112 bytes).

The user found the first fitting image too noisy. A subsequent raw, aligned
spectrogram search tested residual-noise levels and pitch, then refined the
wave dictionary and frame parameters without gain matching. The selected
image is now **1014 bytes plus 64 EEPROM**. The spectral refinement uses
256/1024-sample STFTs and a declared intelligibility floor. Against its initial
998-byte denoised candidate, raw log spectral error falls 0.91836 to 0.82599
and the measured unsupported high-band energy falls 0.00200065 to 0.00094643;
STOI falls 0.70823 to 0.69487. This is an explicit noise/spectral tradeoff,
not a universal quality improvement. The two stages use different objectives.
The same raw evaluation of the unchanged 1022-byte incumbent gives high-band
excess 0.06878833 and STOI 0.724265; the final values are 0.00094643 and
0.694871. The 98.624% measured excess reduction is not a perceptual-noise
percentage. Both input model and script hashes are pinned in the receipt.

The benefit is complete Flash fit and a quieter spectral candidate from offline
representation selection. No speedup or improved runtime RAM is claimed.
All 54144 speech/silence PWM outputs and CPU/memory states agree across JS and
both WASM configurations with IRQ active. There are zero lost samples and
lost overflows, maximum ISR 28 cycles, static SRAM span 10 bytes and observed
stack margin 43 bytes. Physical hardware and extra IRQ load were not measured.

Recipes: `tools/build-shared-tiny-speech.py`, seed 23120, four dictionary starts,
3000 proposals per pitch mode; then `tools/refine-shared-tiny-noise.py`, seed
23121, 800 refinement steps. Rebuild the selected spectral model through the
first tool's `--noise-model` / `--noise-report` options. Full reproduction order
and per-file provenance are retained below. Source duration is preserved;
48 trailing zeros align the existing 64-sample block, yielding 2.4064 seconds.
The prior model's RMS-envelope alignment has zero lag. This does not establish
identical perceived articulation or pitch. Optional firmware gain is omitted.

[Models, exact receipts and constraints](../../ATtiny13A/Sound/research/shared-speech/README.md),
[per-file source/codec/build inventory](../speech-assets.md).
