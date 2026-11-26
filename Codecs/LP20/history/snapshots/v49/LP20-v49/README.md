# LP20 v49 — finite-memory Viterbi PWM search

PC-only encoder experiment building on LP4V/v48. Existing PWM template set, sample libraries, frequency table and rendering model unchanged. No Z80 machine-code build, timing, ROM/RAM verification or board test. Only two previously used recordings; libraries differ by clip, so universal multi-speaker training is not established. Stream byte counts include LP4V header and Huffman lengths, exclude the separate 2048-byte book/DDS tables and decoder. Standalone payload therefore exceeds 6 kb/s. The 25 dB target is still unmet at <=6 kb/s.

## Algorithm
`viterbi49.py`: each sample can retain its current template or move to an adjacent valid template index. A state stores the last M ternary choices. For a 96-sample window, Viterbi minimizes a quadratic local cost with pairwise interactions through M samples. A separate acceptance check evaluates the entire modeled kernel halo (including interactions outside the DP memory) with optional HF and peak penalties. The kernels approximate the existing bin-averaged PWM model, not an electrical measurement. Nonquadratic peak penalties in the trellis are approximate. This is not an exact global optimum of the entire waveform. Windows are shifted and processed in opposite orders in successive passes. `test49.py` checks exactness against exhaustive search in 12 small-window quadratic tests with full memory and boundary indices.

`compare49.py`: two extra four-template passes from the same v48 direct baseline, followed by a separate 729-state Viterbi test starting from the two-pass Viterbi solution. The equal-pass comparison is not an equal-runtime comparison. The third Viterbi pass changes both memory and iteration count, so it does not isolate the effect of memory alone.

| Direct (uncompressed) | First SNR dB | Second SNR dB |
|---|---:|---:|
| v48 quad | 30.862172 | 30.008158 |
| + 2 quad control passes | 30.888678 | 30.025482 |
| + 81-state pass | 31.014866 | 30.159952 |
| + 243-state pass | 31.042613 | 30.178207 |
| + 729-state pass | 31.052615 | 30.189472 |

`refine49.py`: starting from v48 Recommended, construct Viterbi optimized PWM targets with adaptive weighting and a peak penalty; use those targets and an inverse-hold approximation to propose new DCT scales and coefficients. Optimize scale transitions and allocate bits under the actual LP4V cap. Rebuild Huffman lengths only if the stream gets smaller. Existing predictor headers and partition are fixed. The unconstrained target waveform is NOT the waveform decoded from the compressed stream. `blend49.py`: a second optimization mixing compatible complete frames from the Viterbi streams and v48, based on waveform, spectral-valley and local log-spectral error costs. `report49.py`: checks each of the 12 new streams by independent decoding, re-rendering, exact WAV equality and file-size cap, then generates comparisons. The six selected aliases copy already verified bitstreams. `Quality` is experimental, not a strictly dominant replacement for v48 (first clip STOI slightly lower).

## Selected compressed results
| Clip | Profile | Stream bytes | kb/s | SNR dB | Peak % | P99.9 % | STOI | LSD dB |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | v48 Recommended | 15069 | 5.998806 | 24.280799 | 7.621737 | 3.499175 | .794546 | 4.581515 |
| 1 | v49 Quality (Blend-2) | 15068 | 5.998408 | 24.293703 | 7.623128 | 3.484726 | .794079 | 4.574318 |
| 1 | v49 MaxSNR | 15067 | 5.998010 | 24.297479 | 7.622346 | 3.479972 | .792962 | 4.581773 |
| 1 | v48 Compact59 | 14817 | 5.898487 | 24.173269 | 7.622668 | 3.553457 | .786892 | 4.654308 |
| 1 | v49 Compact59 | 14816 | 5.898089 | 24.189039 | 7.622725 | 3.526770 | .789263 | 4.640895 |
| 2 | v48 Recommended | 22462 | 5.999466 | 23.970659 | 7.580417 | 2.673983 | .831196 | 3.888101 |
| 2 | v49 Quality (Blend-2) | 22457 | 5.998130 | 23.984908 | 7.569637 | 2.669220 | .831786 | 3.887662 |
| 2 | v49 MaxSNR | 22464 | 6.000000 | 23.989420 | 7.568152 | 2.670795 | .830393 | 3.884383 |
| 2 | v48 Compact59 | 22087 | 5.899306 | 23.877492 | 7.581870 | 2.763676 | .825447 | 3.943059 |
| 2 | v49 Compact59 | 22083 | 5.898237 | 23.892115 | 7.571646 | 2.742356 | .827246 | 3.942121 |

Quality profiles both pass peak <=8% and P99.9 <=3.5%; first Compact59 does not meet P99.9 <=3.5%. v49 Quality relative to v48 Recommended: +0.01290 / +0.01425 dB SNR, 1/5 fewer stream bytes, STOI -0.000467 / +0.000590. HF voiced and interharmonic proxy errors improve slightly on both. Improvements are too small to infer audibility. v49 MaxSNR has slightly more SNR at the expense of STOI. Keep v48 as the strict reference for first clip; further LPC / sample residual compression changes likely matter more than increasing the DP memory.

Metrics: same 3.5 kHz analysis band, DC removal, one fitted gain and integer delay, first/last 10 ms exclusion, same reference peak as v48. A/B WAV: reference, v48 Recommended, v49 Quality, v49 Compact59; 3 seconds each with 350 ms gaps, one playback scaling after global alignment. All WAVs are simulated, not recorded from a Z80 board.

## Reproduce
Extract sibling directories intact. Python dependencies: numpy, scipy, numba, scikit-learn, pystoi, matplotlib. From `LP20-v49`:
```
python test49.py
python viterbi49.py first
python viterbi49.py second
python compare49.py first
python compare49.py second
python refine49.py first Peak
python refine49.py second Peak
python blend49.py first
python blend49.py second
python report49.py
```
The included cached `compressed-target.npy` files can be removed to recompute targets; `candidates.pkl` intermediate not distributed. Inputs are the original private engineering clips from prior versions. Only the sources and dependencies needed for this study and generated results are packaged, not the old complete version archives.
