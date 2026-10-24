05 · GREENSLEEVES — FOUR COMPLETE SOURCE PARTS

All 235 notes from the retained Z80 four-voice example are now played:
70 soprano/flute (GM73), 52 alto/violin (GM40), 58 tenor/clarinet (GM71),
55 bass/cello (GM42). The earlier three-voice version omitted the clarinet
and sampled only33 alto and33 bass notes. Every source pitch, attack and
NoteOff is retained exactly on the sixteenth grid. The four-voice source
has one tied D4 instead of two written attacks in the other retained edition.
All source notes use velocity90; instrument mix levels are15/12/11/10.

The complete48-quarter-beat tune lasts48 seconds at60 BPM, with its original
6/8 meter, half-beat pickup and2.5-beat closing bar. A separate0.25-beat
silent gap allows all releases to finish; measured loop48.26457875 seconds.
There is no percussion in the source or firmware. No music is removed.

ENGINE AND MEMORY
Flash812/1024bytes:438code +374tables. EEPROM64bytes contains all four
measured low/high wave pairs. Four independent16-bit DDS oscillators retain
phase across attacks. Each part has a linear soft attack and release; no
voice stealing or extra release channels. Shared commands and bounded
Re-Pair rules retain every NoteOn/Off and wait without dropping events.
The generic builder, source arranger, calibration, audit and WAV exporter
are retained in tools/. No SoundFont or MIDI binary is needed for rebuilding.

Real PWM is calibrated over the complete loop: one fixed linear gain128/33,
center128, measured PWM0..237, no clipping or independent half-wave scaling.
The gain lookup covers the proven full mix bounds-33..30 from all measured
waveforms and envelope levels, including every later loop/phase alignment.
The preview has separate post-filter peak normalization to0dBFS.
Full-loop audit:235notes/470events,904959mix and PWM-pair checks, no lost
IRQs or FIFO underruns,393maximum elapsed render cycles (<512),48bytes
worst-case SRAM including stack. See verification.json for pinned hashes.

REPRODUCE FROM THE REPOSITORY ROOT
  python tools/arrange-greensleeves.py
  node tools/audit-compact-four.mjs ATtiny13A/Music/variants/greensleeves
  node tools/render-firmware-preview.mjs ATtiny13A/Music/variants/greensleeves 49 9000 0.5 --normalize

Flash synth.hex and eeprom.hex. ATtiny13A fuses7A/FF, internal9.6MHz RC
without CKDIV8. PWM PB1/OC0B (pin6); VCC8, GND4. Synthesis18.75kHz,
PWM37.5kHz with midpoint interpolation,16-byte FIFO and15-cycle ISR.
FluidR3-MIT.txt covers measured instrument data; the tune/Mutopia edition
is Public Domain. Source provenance is recorded in score.json.
