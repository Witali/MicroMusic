# LP20 v45 — adaptive block length and joint sample/residual search

PC reference study only. No new Z80 machine code. Unchanged v39 PWM template set and bin-averaged PWM render, same metrics / global gain and delay convention as v44. Target >=25 dB, <=6 kb/s; not reached. The two original user recordings are the only test material. The 6-bit sample books (1536 B) and frequency tables (512 B) are unchanged from v44; each book and the Huffman lengths are trained on the opposite recording, not on an independent multi-speaker corpus. Reported stream bytes include format header, 108-byte code-length table, all block parameters, block-size flags, residuals and padding. They exclude the 2048 B sample and frequency tables and any decoder code. No hardware test; 16 KiB/zero RAM/timing requirements unverified for this architecture. In particular, long IDCT blocks may make a Z80 implementation harder.

## Method
- `adaptive45.py`: generate candidate blocks of 128, 256, 512 samples. 256 and 512 aligned to their respective boundaries, 128 allowed on every 128-sample boundary; final block truncated. LP4V extends LP4S with prefix block lengths 0=256, 10=128, 11=512. Differential phase uses previous actual block length. Fixed mode writes standard LP4S. Compare transform-only, original v44 predictor at 256-sample lengths, and new single/morph predictor fits. Quantization candidates from deadzones and sparse rate-aware trellis, local PWM-level feedback. Limited scale / lambda search, beam of 8 distinct predecessor states and global Lagrangian rate allocation. Local proxy errors are not exact full-waveform distortion; no proof of global optimum.
- `evaluate45.py`: same candidate pool, fixed original predictor (fixed-control), joint predictor selection at fixed 256, adaptive length, peak-weighted adaptive, and 5.8 kb/s. More precise 34-iteration rate search, versus initial exploratory 22 iterations in adaptive45.py. Earlier exploratory runs sometimes significantly underfill budget and are not direct equal-rate comparisons.
- `refine45.py`: alternate fitting sample predictor to the target minus quantized residual plus PWM feedback, then reoptimize residual. Only selected voiced blocks are refitted (384 and 588 distinct selected frame states respectively); 3698 and 5607 candidate records added. Library itself unchanged.
- `diag45.py`: direct quantization of original internal PCM with the same PWM renderer, no compression. This is a diagnostic, not a theoretical performance bound. Peak errors remain ~10.9% and 10.3%, even with no compression; suggests further output-domain optimization of input waveform and clipping/headroom. Hardware fixed.
- `report45.py`: re-decode chosen 6 and 5.8 kb/s streams, assert WAV sample equality, compare globally aligned and 3.5 kHz filtered waveform, spectrum and peaks. A/B file order: reference, v44 Strict6, v45 5.8, v45 6; 3 seconds each with 350 ms silence.

## Reproduce
Python 3; numpy, scipy, numba, scikit-learn, pystoi, matplotlib. Extract sibling folders intact. Input subset of v44 is included. From LP20-v45, for each `first` and `second`:

    python adaptive45.py first
    python evaluate45.py first
    python refine45.py first

Then `python diag45.py` and `python report45.py`. Candidate cache is omitted from archive and regenerated. JSON and CSV include exploratory and final runs. All streams were serialized, decoded and checked against chosen model PCM during generation. The recommended profiles were independently rerendered and verified against saved WAVs. No broad corpus validation or listening test.

## Selected results (stream only)
| profile | first kb/s | first SNR dB | second kb/s | second SNR dB |
|---|---:|---:|---:|---:|
| v44 Strict6 | 5.99920 | 23.85665 | 5.99973 | 23.44159 |
| v45 fixed-control | 5.99920 | 23.87815 | 5.99947 | 23.46031 |
| v45 joint256-tight | 5.99960 | 23.90007 | 6.00000 | 23.49262 |
| v45 adaptive-tight | 5.99920 | 24.06816 | 6.00000 | 23.67005 |
| v45 adaptive-refit | 5.99841 | 24.09376 | 5.99973 | 23.69118 |
| v45 adaptive58-tight | 5.79857 | 23.89716 | 5.79888 | 23.50257 |

Peak maxima not improved by recommended new profiles (slight increase); p99.9, STOI, LSD, spectral convergence, high-frequency and harmonic-valley error improve at 6 kb/s relative to v44 Strict6. The 5.8 kb/s mode preserves or improves most quality metrics but maximum error remains. Further pursue adaptive lengths (64, 384, and restricted max block length for eventual Z80), actual full-PWM-domain feedback and peak constraints, and jointly fit multiple sample candidates. No changes to circuit.
