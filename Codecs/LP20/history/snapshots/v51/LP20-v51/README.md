# LP20 v51 — nonlinear PWM + Viterbi + rate-constrained residual refinement

PC-only research, not a Z80 firmware release. Two private speech examples from LP20. Target PCM 7812.5 Hz, 8 PWM periods/sample, 320 T/period at 20 MHz. The physical circuit is unchanged in the model. Exact 255-pattern table is shared between both examples. The sample books remain per-recording (cross-recording-trained in the earlier study); no independent corpus was obtained.

## Algorithm and verification
- Start from v49 Quality LP4V coefficients, rendered with v50's fixed 255-level power-law grid (gamma 1.7). Check the v50 baseline WAV sample-for-sample.
- Build phase-specific impulse-response tables for the 255 actual pulse patterns. Reuse v49 finite-memory Viterbi (81 and 243 states; 96-sample windows, full-window acceptance). Direct tests are **unconstrained**; their arbitrary level trajectories are not stored in a 6 kb/s stream.
- Refine residual DCT coefficients and scale indices with rate-aware search under existing LP4V syntax, using Viterbi target deltas and backprojected output error. Candidates are rendered through the actual bin-averaged PWM model and weighted by amplitude, high-frequency error and peak penalties; global scale-state allocation accounts for the actual transmitted bits. Two passes for first clip, three for second. The final selection is highest SNR subject to stream <=6 kb/s, peak <=8%, p99.9 <=3.5%. It does not enforce historical v39 STOI. All 12 new candidate streams are independently decoded in report51.py and compared byte-for-byte to saved WAV sample arrays. The old sample-predictor headers remain unchanged. No new transmitted per-sample PWM index: quantizer maps the decoded internal waveform to the expanded grid.
- Fixed gamma 1.7 was better in SNR on both unchanged v49 streams than 5 other 255-grid candidates including cross-recording trained histogram-based grids; this is NOT a speaker-independent corpus evaluation.
- Exact packed PWM storage: full 255x4 = 1020 bytes. Symmetry (negative pattern = 320 minus each positive width, reverse level index) reduces storage to 128x4 = 512 bytes. The central pattern is all 160. A two-page 512-byte mapping (base index per signed high byte and packed three 2-bit fractional offsets) is verified on every 10-bit PCM code. Combined symmetric data tables = 1024 bytes. This excludes dispatcher machine code, index arithmetic and any width/fragment-address tables; the legacy ROM-threaded decoder cannot read this data directly. No verified cycle budget or Z80 ROM/RAM claim. The old 6-bit exact mapping is insufficient: 40 of 256 input quartets span two output index steps rather than one.

## Selected results (measured after modeled PWM)
| Profile | First bitrate kb/s | First SNR dB | First peak % | Second bitrate kb/s | Second SNR dB | Second peak % |
|---|---:|---:|---:|---:|---:|---:|
| v49 Quality | 5.998408 | 24.293703 | 7.623128 | 5.998130 | 23.984908 | 7.569637 |
| v50 255 | 5.998408 | 24.831232 | 8.304207 | 5.998130 | 24.487637 | 6.623053 |
| v51 Quality | 5.998806 | 25.230650 | 6.732920 | 5.999466 | 25.015170 | 5.808081 |
| v51 Compact59 | 5.898885 | 25.017330 | 6.741912 | 5.898237 | 24.719343 | 6.282610 |

Quality: first 15069 B, second 22462 B. Stream bytes include header and Huffman lengths but exclude 2048 B sample/DDS books and PWM tables. With 1024 B symmetric data and 2048 B books, effective rates before machine code are about 7.22/6.82 kb/s for these short recordings. 25 dB/6 kb/s has been achieved in the stream-only PC simulation on both examples, not demonstrated on Z80 or on a wider corpus. STOI 0.805718/0.837379 remains below v39 (~0.824/0.868). Metrics use same prior procedure: 3.5 kHz band, globally fitted gain and delay, DC removal, exclude 10 ms at each end; no independent subjective listening test. Filter model is bin-averaged PWM and offline zero-phase filters, not a measured analog board response. Direct 255-level Viterbi SNR 34.393339/34.521587 dB, peak 8.955/9.595% in SNR mode; peak-prioritized unconstrained trajectories 34.078883/34.159637 dB and peak 7.057/5.120%. AB files have reference, v49, v50, v51 Quality, v51 Compact59 in sequence, common gain after global alignment.

## Reproduce
Extract sibling directories intact. Install numpy, scipy, numba, scikit-learn, pystoi, matplotlib. From LP20-v51:
```
python compact_lookup.py
python grid51.py first
python grid51.py second
python grid_cross.py
python refine51.py first Peak
python refine51.py second Peak
python refine51.py first Peak 2
python refine51.py second Peak 2
python refine51.py second Peak 3
python report51.py
```
Archive includes required prior source modules and data. `Quality.lp4v` and `Compact59.lp4v` use existing LP4V syntax and require their matching `book.bin` and the v51 255-grid renderer. `pwm255-half.bin`, `pcm-to-pwm255.bin` are verified data layouts only, NOT Z80 executable binaries. `comparison.csv` contains all candidate measurements and baseline values; `selected.csv` contains the four selected profiles. `grid-cross.json` and per-clip `direct.json` contain separate model experiments. No hardware, 16 KiB executable size, or 0 RAM validation performed.
