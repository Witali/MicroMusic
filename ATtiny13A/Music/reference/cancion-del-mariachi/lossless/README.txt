LOSSLESS NOTE PACKING · CANCIÓN DEL MARIACHI

MNC1 stores both original guitar parts without selecting upper voices or
removing chord tones. The verified payload sizes are:

Selection                       Notes   Peak notes at once   Payload bytes
Source beats 58..121              1027           7                 349
All music after beat 58           4166           8                 890
Whole source, including intro     4237           8                1030

These are byte counts of packedData, including the MNC1 header and its
dictionaries. The surrounding JSON, source metadata and decoder/synthesizer
code are additional. full-no-intro.json is the complete requested selection;
excerpt.json is the shorter passage used by the current AVR arrangement.

Preserved exactly: track and channel, program, every pitch (including inner
chord tones), Note On and Off ticks, repeated attacks, On/Off velocities,
rests, within-chord pitch order and PPQN. Selecting an interval includes all
attacks in [startBeat,endBeat), retaining each complete original Note Off.
The packets round-trip to the original records, independently paired by a
separate test implementation. Source and decoded-note SHA-256 hashes are
included. sourceTempoEvents contains the source's absolute tempo events;
startBeat defines the selection offset. Both parts use GM24 nylon guitar.

This is a note codec, not a byte-for-byte MIDI codec. The complete original
controllers, tempo changes, metadata and raw event order remain in the
adjacent source-events.json. No MIDI binary is needed or retained. Parts
with overlapping different-gate chords, changing programs, incompatible
velocities or unsupported palettes fail explicitly instead of losing notes.

Encoding, version MNC1 (all multi-byte integers use MIDI-style VLQ):
  magic "MNC1", PPQN, tick unit (exact GCD), extent in units, part count.
  Per part: track index VLQ; channel, program, Off velocity; shape count.
  Each shape: byte length and ordered MIDI pitches.
  Rhythm count; each rhythm: gap since previous Off and gate, both VLQ.
  On velocity count and palette (one or two values).
  Base symbol count; each base: shape index and rhythm | velocityIndex<<7.
  Rule count; each rule: two earlier byte-sized symbol IDs.
  Playback symbol count VLQ and the byte stream.

Repeated chord shapes, rest/gate pairs and phrases are shared. The bounded
Re-Pair grammar uses backward references only and maximum expansion depth
eight. A streaming decoder needs a current-symbol register plus at most
eight pending-symbol bytes per part, in addition to cursors, timing and
synthesizer state. No history buffer is required. This is a measured result,
not a claim that the encoding is globally minimal.

Reproduce from the repository root:
  python tools/pack-musical-events.py ATtiny13A/Music/reference/cancion-del-mariachi/source-events.json ATtiny13A/Music/reference/cancion-del-mariachi/lossless/excerpt.json --start-beat 58 --end-beat 121
  python tools/pack-musical-events.py ATtiny13A/Music/reference/cancion-del-mariachi/source-events.json ATtiny13A/Music/reference/cancion-del-mariachi/lossless/full-no-intro.json --start-beat 58
  python tools/pack-musical-events.py ATtiny13A/Music/reference/cancion-del-mariachi/source-events.json ATtiny13A/Music/reference/cancion-del-mariachi/lossless/whole-source.json
  python tools/test-pack-musical-events.py

Use unpack(packet['packedData']) in tools/pack-musical-events.py to restore
ordered note groups. Tests cover all 4237 original notes, the two selections,
random chord sequences, repeated attacks, malformed packets and explicit
rejection of unsupported input.

ATtiny13A status:
The current three-tone AVR kernel does not decode MNC1 or play the seven/eight
simultaneous source notes. The complete no-intro payload alone leaves only
134 of 1024 Flash bytes for all decoder and audio code. These packets are
not advertised as fitting firmware, and the existing reduced AVR player
must not be described as lossless. Playback requires further decoder and
polyphonic engine work or a target with more resources.
