# Pulsebook core compaction, with unchanged PCM

These separate profiles save **16 actual AVR code bytes** from each frozen
pulsebook decoder. Excitation, phase/frame boundaries, EOF sample convention,
lattice products and T1 remain unchanged. No speech quality improvement is
claimed for this code-only pass. The freed bytes can fund a subsequent data
refit under the same complete 1024-byte Flash limit.

| Profile | Previous code | Compact code | Maximum speech stream |
|---|---:|---:|---:|
| Ordinary Q3, floor | 408 | 392 | 631 |
| Ordinary Q3, nearest | 410 | 394 | 629 |
| Extended −15/16 pole, floor | 430 | 414 | 609 |
| Extended −15/16 pole, nearest | 434 | 418 | 605 |

Each maximum is actually assembled as **1024 Flash bytes plus 64 EEPROM
bytes**: executable + complete speech stream + one EOF byte, including linker
alignment. All 64 EEPROM bytes store the four signed 16-sample pulse templates.
They do not also store speech-prefix data. Both HEX files belong to one build.

The savings come from shared initialization and EOF stream entry (4 bytes),
preserving the original header byte while extracting its class (4 bytes),
sharing coefficient-update pointer/count setup (6 bytes), and extracting the
high coefficient nibble in its own register without a copy (2 bytes).
The update parser may leave different values in dead scratch registers; its
live pitch/gain/mode/coefficient, T flag and stream-pointer results are preserved.

`tools/build-q3-pulsebook-compact.py` accepts `--rounded` and `--pole`
independently. Its Python API is
`build(stream_path, table_path, output, avr_bin=None, node='node', *,
rounded=False, pole=False, expected_samples=None)`.
Raw signed 64-byte tables and JSON arrays/models with `pulsebook` are accepted.
Ordinary Q3 rejects nibble zero; only the explicitly selected pole profile
maps it to −15/16. This distinction does not change during compaction.

`tools/test-q3-pulsebook-compact-avr.py` has four focused tests. Eight real
before/after firmware images preserve identical stream, EEPROM and output PCM
for noise, all source modes, full/low/high/repeat coefficient updates, compact
and extended headers, short periods, and EOF silence. All images pass the
reference, WASM and unoptimized WASM engines. Measured minimum preparation
slack for these paired inputs changes from 459→464, 443→449, 501→506 and
485→488 cycles respectively at 9.6 MHz/7500 Hz. These are case measurements,
not a universal timing bound for all possible streams.

The tests also assemble all four exact maximum-size images, reject larger
streams and accidental format crossing, and execute the actual AVR multiplier
for all signed bytes and all sixteen coefficient codes in all three engines:
**49,152 products**, including the extended-pole −128 case. Source/EEPROM/PCM
hashes, before/after comparisons and timing reports remain under ignored
`build/q3-pulsebook-compact-validation/`. Physical hardware is untested.

```powershell
python tools/test-q3-pulsebook-compact-avr.py
python tools/build-q3-pulsebook-compact.py --stream speech.hq --table eeprom.bin --samples 22272 --output build/compact-speech --avr-bin <avr-bin> --node <node>
```
