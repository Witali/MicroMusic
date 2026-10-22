# Original input clips (private-use archive)

The three MP3 recordings were provided by the user. They and the derived
encoded/decoded speech must **not** be distributed in the public source ZIP.

Conversion/preprocessing script:

```bash
python convert_audio.py --input inputs/xtuj-ntt.mp3 --output prepared/chego.wav --start-samples 275 --samples 9216 --peak 0.90
python convert_audio.py --input inputs/ne-otv.mp3 --output prepared/otvechaesh.wav --start-samples 576 --samples 7936 --peak 0.90
python convert_audio.py --input inputs/vinni-pux-3654654.mp3 --output prepared/vinni.wav --start-samples 1200 --samples 22272 --peak 0.55
```

These commands produce valid 7500-Hz mono 16-bit WAV inputs. The canonical
`references/*/original.wav` were prepared earlier using slightly different
normalization and filtering; **they are the exact files used for published STOI
values and for the saved trained.npz coefficients**. Do not silently swap them
when comparing historical metrics.

The trained files can be decoded and turned into real ATtiny13A HEX plus WAV
without rerunning optimization:

```bash
python run_all.py
```

Optional extra optimization on these same clips (does NOT guarantee 0.9 STOI):

```bash
python run_all.py --optimize --seconds 60
```
