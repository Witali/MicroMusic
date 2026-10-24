# Canonical speech recordings

These three mono 7500 Hz, 16-bit PCM WAV files are copied byte-for-byte from the
canonical references recorded in
[`audio-references.json`](../../../ATtiny13A/Sound/audio-references.json).
They are the public source recordings offered by the speech player's
original WAV link. Variants of one phrase share one URL.

| File | Samples | Duration | SHA-256 |
| --- | ---: | ---: | --- |
| `chego.wav` | 9216 | 1.2288 s | `c6cdbd26696bdd11695f2491f1558dd246a6f8109fd400e37d292a4d38cdb08c` |
| `otvechaesh.wav` | 7936 | 1.058133 s | `96c09f80396643dd80efb9c5c8557d83359eeb829a0b855a7f8f5c32bbff0b96` |
| `vinni.wav` | 22272 | 2.9696 s | `749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03` |

The catalog generator verifies the file hashes and WAV formats. Generated
firmware captures, listening comparisons and temporary audio stay in ignored
`build/` directories.

The “Прослушать оригинал” button uses mono 44,100 Hz, 16-bit PCM WAV copies
in `playback/`. Mobile media decoders may reject the nonstandard 7500 Hz
canonical rate. The copies use filtered resampling with unchanged speed,
pitch and level; no speech codec or firmware output is involved. The reference
link and all source hashes still identify the byte-for-byte canonical files.

Regenerate with `python tools/prepare-original-audio.py` (requires FFmpeg),
then rebuild the catalog with `python tools/build-hq4-catalog.py`.
Verify retained copies without FFmpeg using
`python tools/prepare-original-audio.py --check`.
`playback/manifest.json` records the resampler, FFmpeg version, source hashes,
output hashes, sample rates and sample counts.
