# New phrase trials

Compressed source models and independent AVR qualification are retained here. Original MP3/WAV, assembled binaries and optimizer checkpoints remain outside Git. Input reports preserve external source filenames, SHA-256, preprocessing and any requested excerpt boundaries.

Selections are provisional comparisons of the same exact AVR PCM using STOI, deterministic eSTOI and the common multi-resolution spectral objective. Human listening and physical hardware tests are not claimed. Nonselected verified models preserve useful negative evidence.

HQ4: rebuild each `speech.hq` using `tools/build-hq4-oneshot.py --stream <stream> --clip <id> --samples <reference_samples> --output <build-directory>`. Tiny: rebuild its `model.json` using `tools/build-tiny-speech.py --model <model> --output <build-directory> --play-once`. Refer to the hybrid model and builder when the selected family is hybrid.
