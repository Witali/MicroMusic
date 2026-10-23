MIDI binaries are not retained. greensleeves-events.json and greensleeves-4voices-events.json preserve all source events, tracks, instruments and original SMF SHA-256. External source paths below identify provenance.

Greensleeves — unchanged source score from the Z80 web player
==========================================================

Copied without modification from:
  C:/Work/z80-tester/audio/assets/scores/midi-examples/greensleeves.mid
  C:/Work/z80-tester/audio/assets/scores/midi-examples/greensleeves.ly
  C:/Work/z80-tester/audio/assets/scores/midi-examples/greensleeves.rdf
  C:/Work/z80-tester/audio/assets/scores/midi-examples/greensleeves-4voices.mid

Traditional English melody; typeset by Steve Dunlop.
Edition: Mutopia-2014/03/30-1247. The LilyPond and RDF records declare
Public Domain. Original source stated by the edition: www.cyberhymnal.org.
The Z80 repository's README records download from Mutopia on 2026-10-15.
greensleeves.mid is the original two-staff SATB source used to produce the
Z80 player's four-channel greensleeves-4voices.mid example, not a recording.
The original MIDI has no Program Change. The actual example, selected by
the Z80 examples.json registry, explicitly assigns zero-based GM programs
73 (flute), 40 (violin), 71 (clarinet), and 42 (cello). These assignments are
also visible in audio/lib/midi-firmware/src/build_examples.mjs in that repo.

The ATtiny13A adaptation uses the complete written soprano on flute, with
independent Alto/Violin and Bass/Cello pitches sampled at dotted-quarter
boundaries. Tenor/Clarinet is explicitly omitted to fit three tonal voices;
no synthetic guitar or percussion is added. Its score.json records hashes,
conversion details and the
single MIDI legato overlap reduced to the written monophonic duration.
The original files in this directory remain unchanged. Rebuild using
tools/arrange-greensleeves.py; details in variants/greensleeves/README.txt.

flute-measurements.json and cello-measurements.json retain measured harmonic
frames/envelopes used by the shared build-time instrument bank. Each records
original FluidR3 GM3.1 SHA-256, renderer SHA-256, exact program, capture WAV
hashes, note ranges, gate/tail, window and analysis settings. The large SF2 and
temporary WAV files are external/ignored; firmware rebuilding needs neither.
The generic capture tool names its profile/file prefix "violin" even with a
--program override; the preset/program fields correctly identify Flute73 or
Cello42. These are SoundFont reference measurements, not acoustic recordings.

To reproduce measurements with the pinned external SF2 and SpessaSynth:
  node tools/render-fluid-violin.mjs --soundfont ORIGINAL.sf2 --engine spessasynth.js --output build/greensleeves/flute --profile violin --program 73 --notes 59,64,69,74 --gate 2 --tail 1
  node tools/render-fluid-violin.mjs --soundfont ORIGINAL.sf2 --engine spessasynth.js --output build/greensleeves/cello --profile violin --program 42 --notes 47,50,52,55 --gate 2 --tail 1
  python tools/analyze-fluid-violin.py build/greensleeves/flute ATtiny13A/Music/reference/greensleeves/flute-measurements.json
  python tools/analyze-fluid-violin.py build/greensleeves/cello ATtiny13A/Music/reference/greensleeves/cello-measurements.json

Upstream identifiers retained as provenance, not as fetched web evidence:
  https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=1247
  https://www.mutopiaproject.org/ftp/Traditional/greensleeves/greensleeves.mid
