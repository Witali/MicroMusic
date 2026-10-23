#!/usr/bin/env python3
"""Build a private fully reproducible research archive and audio-free source archive."""
from pathlib import Path
import shutil,zipfile,json,os
W=Path(__file__).resolve().parent
P=Path('/mnt/data/MicroMusic_HQ4_Project')
Q=Path('/mnt/data/MicroMusic_HQ4_Source')
for target in [P,Q]:
    if target.exists():shutil.rmtree(target)
    target.mkdir(parents=True)

scripts=['hq4_core.py','optimize_hq4.py','refine_boundaries.py','refine_timbre.py','build_hq4.py','verify_hq4.js','make_player_hq4.py','package_hq4.py']
for script in scripts:
    shutil.copy2(W/script,P/script);shutil.copy2(W/script,Q/script)
# Remove one sandbox-bound export line from the distributable player generator.
for directory in [P,Q]:
    path=directory/'make_player_hq4.py'
    s=path.read_text().replace("Path('/mnt/data/MicroMusic_MiniLPC_HQ4.html').write_text(htmltext)\n",'')
    path.write_text(s)
shutil.copy2(W/'MicroMusic_MiniLPC_HQ2'/'model.py',P/'model.py')
shutil.copy2(W/'MicroMusic_MiniLPC_HQ2'/'model.py',Q/'model.py')
shutil.copy2(W/'MicroMusic_MiniLPC_HQ2'/'convert_audio.py',P/'convert_audio.py')
shutil.copy2(W/'MicroMusic_MiniLPC_HQ2'/'convert_audio.py',Q/'convert_audio.py')
# Record compressed streams and best training parameters in the PRIVATE project.
for n in ['chego','otvechaesh','vinni']:
    a=P/'MicroMusic_MulQ4_Opt_release'/n;a.mkdir(parents=True)
    for f in ['firmware.S','speech.hq']:
        shutil.copy2(W/'MicroMusic_MulQ4_Opt_release'/n/f,a/f)
    b=P/'MicroMusic_HQ3_Verified_Release'/n;b.mkdir(parents=True)
    for f in ['original.wav','hq.wav','lpx3.wav']:
        shutil.copy2(W/'MicroMusic_HQ3_Verified_Release'/n/f,b/f)
    c=P/'trained'/n;c.mkdir(parents=True)
    for f in (W/'trained'/n).glob('*'):
        if f.is_file():shutil.copy2(f,c/f.name)
    z=Q/'avrfw_source'/n;z.mkdir(parents=True)
    shutil.copy2(W/'MicroMusic_MulQ4_Opt_release'/n/'firmware.S',z/'firmware.S')
shutil.copy2(W/'MicroMusic_MulQ4_Opt_release'/'avr_emulator.js',P/'MicroMusic_MulQ4_Opt_release'/'avr_emulator.js')
shutil.copy2(W/'MicroMusic_MulQ4_Opt_release'/'avr_emulator.js',Q/'avr_emulator.js')
shutil.copytree(W/'release',P/'release',ignore=shutil.ignore_patterns('*.o'))
shutil.copy2(Path('/mnt/data/MicroMusic_MiniLPC_HQ4.html'),P/'MicroMusic_MiniLPC_HQ4.html')
for d in [P,Q]:
    (d/'requirements.txt').write_text('numpy\nnumba\nscipy\nsoundfile\npystoi\n')

README='''# MicroMusic MiniLPC HQ4 — ATtiny13A speech experiments

## Results (confirmed from AVR HEX)

| Speech | HQ3 STOI | HQ4 balanced STOI | Flash size (code + voice) |
|---|---:|---:|---:|
| Chego tebe nuzhno? | 0.89484 | 0.90060 | 959 bytes |
| Chto zh ty ne otvechaesh? | 0.81619 | 0.81906 | 885 bytes |
| Sova! Otkryvay! Medved prishel! | 0.85518 | 0.85960 | 1024 bytes |

There is also an **HQ4 maximum-STOI** firmware for the first phrase: **0.90182 STOI, 957 bytes Flash**. Its spectral-envelope mismatch is higher than the balanced version, so both versions are preserved. HTML lets you hear both.

The ATtiny13A decoder occupies **406 bytes**, including vectors and startup, and uses a signed 8-stage LPC lattice with four excitation profiles. F_CPU = 9.6 MHz (CKDIV8 disabled by software), Fast PWM 37.5 kHz via PB1/OC0B, 7.5 kHz sample rate. EEPROM is not required.

Measured against the supplied recordings: 39,424 total output samples, 0 differences between exact numerical model and the assembled AVR interpreter, 0 missed Timer0 overflow events. Maximum ISR 28 CPU cycles. Tested digitally only, NOT on the physical microcontroller. STOI measures intelligibility, not identity/naturalness of voice.

## Files

- `MicroMusic_MiniLPC_HQ4.html` or `release/index.html`: offline Web Audio player, real AVR interpreter for verification and comparison (original / HQ3 / HQ4 balanced / HQ4 max / LPX3).
- `release/<clip>/firmware.hex`, `firmware.bin`, `firmware.S`, `speech.hq`: three actual AVR variants with compressed speech.
- `release/chego_stoi_max/`: first phrase, highest STOI variant.
- `release/<clip>/AB.wav`: RMS-leveled original, HQ3, original, HQ4 balanced, LPX3 comparison.
- `trained/<clip>/best.npz`: quantized LPC frames and frame lengths, saved after optimization.
- `optimize_hq4.py`: feedback encoder, frame parameter optimization with total Flash and click limits.
- `refine_boundaries.py`: optimized frame boundaries (64/128/192/256 audio samples per frame).
- `refine_timbre.py`: optimize spectral-envelope error while respecting a minimum STOI.
- `convert_audio.py`: MP3/WAV to normalized mono WAV preprocessing (check `--help`).
- `build_hq4.py`: assembler, PCM model verification, creates HEX/PCM/WAV/report and invokes `verify_hq4.js`.
- `make_player_hq4.py`: produces standalone HTML player with embedded files.
- `hq4_core.py`, `model.py`, `verify_hq4.js`: exact arithmetic model and cycle-based AVR emulator.

## Rebuild, verify and train

Requirements: Python 3 with `pip install -r requirements.txt`, `clang -target avr`, `llvm-objcopy`, Node.js.

```bash
python build_hq4.py
python make_player_hq4.py
```

The scripts reproduce the **balanced** three firmware images. After copying this project anywhere, the full private archive includes all reference WAV and training parameters.

Run a new parameter search, then regenerate all binaries:

```bash
python optimize_hq4.py --clip chego --seconds 60 --seed 42
python refine_boundaries.py --clip chego --passes 8
python refine_timbre.py --clip chego --floor 0.900 --seconds 30
python build_hq4.py
python make_player_hq4.py
```

Optimization searches are explicitly best-effort. If no better values are found, the preserved `trained` snapshots remain reproducible. Keep a backup before running the optional retraining commands.

## Intellectual property

The original film excerpts and speech-derived firmware are included **solely for private evaluation**. Do not publish those recordings or their derived speech data to a public GitHub repository without appropriate rights. The audio-free code archive is separately provided for source review; it is not by itself a complete training dataset.
'''
(P/'README.md').write_text(README)
(Q/'README.md').write_text('''# MiniLPC-HQ4 — audio-free source code

Includes: AVRx assembly algorithm, exact Python synthesis model, frame converter/encoder experiments, and cycle-counting JavaScript AVR emulator.

The three cartoon speech recordings, embedded test WAVs, `.hq` voice streams and trained frame/parameter arrays are intentionally excluded. Thus this code-only bundle is *not* the complete runnable reproduction of the private evaluation. To train on your own voice, prepare original WAV at 7500 Hz, create training frame arrays and provide a frame-generation flow using these scripts (the trainer expects an initial MiniLPC stream). Refer to the private research package if authorized.

ATtiny13A: 1024-byte Flash, 64-byte EEPROM, 64-byte SRAM, 9.6 MHz CPU. Code-only archive does not contain a ready-to-flash speech image.
''')

def pack(base,out):
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for f in sorted(base.rglob('*')):
            if f.is_file() and f.suffix not in ('.o',):
                z.write(f,f.relative_to(base.parent))
    with zipfile.ZipFile(out) as z:
        bad=z.testzip()
        assert not bad,bad
        print(out,'count',len(z.namelist()),'bytes',out.stat().st_size)
pack(P,Path('/mnt/data/MicroMusic_HQ4_Private_Project.zip'))
pack(Q,Path('/mnt/data/MicroMusic_HQ4_Code_Only.zip'))
print('DONE: project at',P)
