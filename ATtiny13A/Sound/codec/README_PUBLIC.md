# MicroMusic MiniLPC-HQ2 — source-only kit

Contains the AVR source template, a synthetic demonstration and reproducible
conversion, optimization, emulation and packaging scripts. **No copyrighted
speech samples, phrase-specific encoded data, or fitted parameter files.**

To verify the small synthetic demo:

```bash
python -m pip install -r requirements.txt
python build_demo.py
node demo_verify.js
```

To experiment with real recordings, add WAVs under `references/<clip>/original.wav`
(7500 Hz mono, exact number of samples), optionally using `convert_audio.py`.
The optimization scripts also require starting reflection coefficients and
frame-duration schedules in `samples/<clip>/trained.npz` or a corresponding
`baselines/<clip>_refined.npz`. The private example archive contains these
trained starting models for the three example clips. A new unrelated phrase
requires an initial analysis/quantization pass; no generic high-quality
initializer is claimed in this experimental source-only kit.

For the current two short voice clips and the Winnie-the-Pooh phrase, see the
private archive for all fitting data and the exact audio references.
