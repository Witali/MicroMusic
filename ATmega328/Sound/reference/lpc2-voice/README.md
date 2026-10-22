# MicroMusic · LPC2 Voice v2 (experimental)

Fixes a systematic LPC2 Improved v11 voice-timbre regression on high-pitched voices. The original LPC2 pitch range was hardcoded to 55–420 Hz. Many intervals in the two new recordings exceed that limit, which makes their reconstructed voices noticeably lower.

**The output is a full LPC2 decoder for the browser/computer, not firmware for ATtiny13A.** Existing ATtiny13A LPC-7/8 firmware has its own data format and has not been modified by this change.

## Format change

* `LPC2` magic is unchanged; container version at offset 4 is now **2**.
* `uint16 LE` pitch minimum at offset 32; `uint16 LE` pitch maximum at offset 34 (previously a zero-filled reserved field).
* Pitch is still encoded as 6 bits per voiced frame. No extra per-frame bits or extra 36-byte header overhead. This trades quantization resolution for a more suitable pitch range. Automatic script chooses the range per recording.
* The updated browser decoder supports both LPC2 v1 (fixed 55–420 Hz) and v2 (self-described pitch range). Old v1 decoders cannot read v2; do not rename a v2 stream to v1.
* LPC2 order-10 LSF, voice excitation and 8-subframe interpolation remain the same. The full timbre is not preserved exactly: source pulse shape, fine spectral detail, breathiness and formant trajectories remain imperfect.

## Offline guided encoding and A/B testing

The experimental `run_experiments.py` uses Python pYIN to derive a candidate F0 contour from each source clip; tests pitch bounds, guided/unguided estimation, and postfilter strengths; compares against old LPC2 using STOI and a frame-normalized spectral error; and saves all rendered files. Quality metrics are not equivalent to subjective similarity.

One command to regenerate **with the existing MicroMusic MultiPhrase project present**:

```sh
python build_encoder.py
python run_experiments.py --clips xtuj-ntt ne-otv vinni
python make_release.py
```

To run in a different directory, set `MICROMUSIC_DATA_ROOT` to the directory containing `release/<clip>/source.wav`, `release/<clip>/lpc2.wav`, and (optionally) `<clip>/teacher.lp2`. Requires dependencies from `requirements.txt` and Chromium/Playwright; initial setup may require `python -m playwright install chromium`.

## Comparisons on source clips

| Phrase | LPC2 v1 STOI | Voice v2 STOI | Spectral discrepancy v1→v2 |
|---|---:|---:|---:|
| «Чего тебе нужно?» | 0.567 | 0.620 (automatic; 0.624 guided) | 0.762 → 0.529 (automatic; 0.542 guided) |
| «Что ж ты не отвечаешь?» | 0.527 | 0.585 (guided) | 0.673 → 0.532 |

These are the measured outcomes of this experimental encode/decode pipeline, not hardware benchmarks. For the original Winnie-the-Pooh voice, the earlier v1 render has lower spectral error, so this project retains v1 as the default for that sample.

## Practical guidance

* For a low voice select a narrower F0 range; high voice values around 170–670 or 290–800 Hz worked well for these clips. Use the browser codec's `Диапазон голоса (F₀)` control.
* The Python script's original-F0 guidance is currently more reliable than the browser's pitch-only analysis on some voices; the browser UI does **not** run Python pYIN and will not necessarily reproduce the guided checkpoint.
* Postfilter 10% tended to retain a smoother spectral color than the previous 35% setting on these samples.
* Use the autonomous Web Audio player in `release/index.html` for listening on phones. If the app's viewer disallows audio, use `release/<clip>/AB.wav`.
* User-uploaded cartoon sound recordings and derived bitstreams are **private experiment content**. The `code.zip` excludes all audio and LPC2 phrase files; do not distribute them publicly without appropriate permissions.
