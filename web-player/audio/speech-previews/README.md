# Published speech previews

`vinni-q5.wav` is the exact 22272-sample, mono 7500 Hz output of the retained
Q5 model, represented as signed PCM16 without gain adjustment or filtering.
Its measured STOI is 0.893135861645246; the spectral loss is 0.3848495216978015.
The full original and the selected HQ4 firmware remain available in the player.

`vinni-q5-playback.wav` is a 44.1 kHz listening copy for mobile media decoders.
Only the sample rate changes, using the resampler recorded in `manifest.json`.
The download button offers the canonical 7500 Hz file. Metrics refer to that
canonical output, not to a newly measured score on the listening copy.

This is a PC prototype. Its complete AVR player, timing and 1024-byte Flash
budget have not been qualified. The page lists Q5 beside the existing firmware versions and plays it with
the main transport controls. It offers a WAV download for the prototype.

The model, source commit, original hash, PCM hash, file hashes and measured
results are linked in `manifest.json` and `vinni-q5.json`. Reproduce from the
research checkout at the manifest's pinned commit with NumPy, Numba and SciPy:

```powershell
python tools/publish-speech-preview.py --source-root C:/Work/MicroMusic/.worktree/speech-quality
python tools/publish-speech-preview.py --check
```

The check command needs only the standard library. It verifies audio formats,
duration, model hash and the exact 8-bit decoder output in the canonical WAV.
