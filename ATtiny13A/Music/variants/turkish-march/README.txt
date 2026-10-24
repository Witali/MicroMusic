03 · MOZART — TURKISH MARCH, EXTENDED THREE-VOICE PIANO

74 original2/4bars (148quarter beats), followed by the existing four-quarter
D# closing cadence:152quarters,60.397350993seconds at steady151BPM.
The previous version played70sourcebars plus cadence,57.218543046seconds.
The recognizable opening and one-quarter pickup rest are retained.

Three independent piano oscillators now play360 selected right-hand attacks,
74 selected bass attacks including cadence, and37 restored inner chord tones:
471 attacks in total. The old image used two musical oscillators and two
release-only slots. Those slots are removed; space now goes to actual notes.
The third voice uses the same measured acoustic grand piano (GM0), level9;
right hand and bass use levels15 and10.

The right hand retains the highest active source note and repeated attacks
on a sixteenth grid. The bass selects the lowest source identity active half
a quarter into each two-quarter window, preserving its bounded NoteOn/Off.
The added inner tone is the lowest higher left-hand note sharing exactly the
same original onset and NoteOff as that bass note. Missing inner tones are
exact silence, including zero envelope. No invented percussion or bass line.
Full source piano polyphony, other bass attacks and later source sections
remain omitted. The source tempo map is replaced by steady151BPM. This is
an extended adaptation, not a lossless rendering of the complete2819-note MIDI.

ENGINE AND VERIFICATION
Flash1016/1024bytes:532code +484tables. EEPROM64bytes contains three measured
piano low/high pairs and the shared piano attack pair. Three16-bit DDS phases
continue across attacks. Independent piano decay/release envelopes finish
before the next loop. The packed phrase codec preserves every arranged event;
its bounded dictionary search is heuristic, not a global-optimum claim.

The full AVR loop verified718commands,471attacks,37source inner notes,
1132799mix/PWM pairs and all508voice initializations, including silence.
No lost timer events or FIFO underruns; maximum elapsed render255cycles
against512available, ISR15cycles, worst-case SRAM37bytes including stack.
Timing deviation from the steady score is below13.264ms. See verification.json.
Actual PWM mix range is-56..31 around128; no extra MCU master gain is inserted
because the remaining Flash is used for source music. preview.wav is separately
peak normalized to0dBFS after the player's35Hz/9kHz filters, without clipping.

REBUILD FROM THE REPOSITORY ROOT
  python tools/arrange-turkish-march.py
  node tools/audit-turkish-three.mjs ATtiny13A/Music/variants/turkish-march
  node tools/render-firmware-preview.mjs ATtiny13A/Music/variants/turkish-march 61 9000 0.5 --normalize

The default deterministic4096-candidate packing search can take several minutes.
Scripts, JSON source events, measured banks and generated AVR assembly are all
retained. No MIDI binary or SoundFont is needed for a normal rebuild.
Flash synth.hex and eeprom.hex; ATtiny13A fuses7A/FF, internal9.6MHz RC,
CKDIV8 disabled. PWM PB1/OC0B pin6; VCC8, GND4. Synthesis18.75kHz,
PWM37.5kHz, midpoint interpolation,16-byte ring and15-cycle ISR.
FluidR3-MIT.txt covers measured timbres. Source attribution: Bernd Krüger,
piano-midi.de, edition2013-07-15; original events and source hashes are recorded
in ../../reference/turkish-march/source-events.json and score.json.
