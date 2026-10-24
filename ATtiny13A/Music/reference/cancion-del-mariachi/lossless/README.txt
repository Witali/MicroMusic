LOSSLESS NOTE PACKING · CANCIÓN DEL MARIACHI

MNC1 stores both original guitar parts without selecting upper voices or
removing chord tones. The verified payload sizes are:

Selection                       Notes   Peak notes at once   Payload bytes
Source beats 58..121              1027           7                 349
All music after beat 58           4166           8                 890
Whole source, including intro     4237           8                1030

These are byte counts of packedData, including the MNC1 header and its
dictionaries. The surrounding JSON, source metadata and decoder/synthesizer
code are additional. full-no-intro.json holds the complete no-intro source;
excerpt.json is the shorter passage used by the eight-voice AVR player.

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

ATtiny13A complete excerpt player:
A dedicated compiler now fits all 1027 excerpt notes in a complete 926-byte
AVR image: 574 code bytes and 352 bytes of tables, including precomputed DDS
steps. It shares fixed-size two/six-tone guitar shapes, gap/gate pairs and
binary phrase rules. It does not directly decode the archival MNC1 packets.
Two source guitar parts use eight independent 16-bit phase/step oscillators;
the selected excerpt holds at most seven notes simultaneously. Shared plucked
envelopes preserve the common gates of each source chord. No inner chord
tones or repeat attacks are removed. Both source programs are GM24.

The independent full-loop AVR audit compares every ordered chord and Note
Off against the raw source JSON, checks each mixed tone and every physical
PWM byte, and verifies queue/stack bounds. All 1027 notes and 261 chord attacks
pass; timing error stays below 14.19 ms at nominal 9.6 MHz, DDS error below
2.16 cents. No lost timer/work events or underruns occur. Peak SRAM is 61/64
bytes (32 phase/step, 16 PWM ring, 7 pending phrase symbols, 6 hardware stack).
This is emulation evidence; short FluidR3 waves approximate the guitar timbre.
The second guitar has separate, circularly smoothed nylon waves in EEPROM
and half gain (-6.02 dB) after its envelope. The lead profile, every source
note and the original gates remain intact. Four waves occupy 32 EEPROM bytes.

Reproduce the complete player:
  python tools/build-mariachi-lossless.py --output ATtiny13A/Music/variants/cancion-del-mariachi-polyphonic
  node tools/audit-mariachi-lossless.mjs ATtiny13A/Music/variants/cancion-del-mariachi-polyphonic
  node tools/render-firmware-preview.mjs ATtiny13A/Music/variants/cancion-del-mariachi-polyphonic 30.9
Firmware, compiled-score.json and verification.json are in that variant.
The player ID cancion-del-mariachi now selects this complete excerpt; the
previous reduced arrangement remains cancion-del-mariachi-ensemble.

The full 122-second no-intro song is not included in this firmware. Its MNC1
payload alone leaves only 134 of 1024 Flash bytes for code. The excerpt's
measured fit must not be extrapolated to that longer selection.

Earlier eight-voice synthesis feasibility probe (retained for comparison):
  python tools/probe-eight-guitar-voices.py
  node tools/audit-eight-guitar-voices.mjs
The static AVR probe has eight independent 16-bit DDS phases and steps,
using the measured nylon guitar EEPROM waves. It sums each guitar chord
before applying its shared gain with signed 16-bit arithmetic. No chord
tone is removed. Code is 212 bytes plus a 16-byte demonstration pitch table.
At 18,750 synthesis samples/s it takes at most 442 active cycles, within
512 CPU cycles per output. A one-second emulation verifies 149984 phase
advances, 18748 complete mixes/PWM pairs and all 1456 signed chord-gain cases, with
no lost timer events or PWM underruns. SRAM usage is 50 bytes in this probe,
including the observed two-byte stack; gain values live in registers.
The retained report is eight-voice-synthesis-probe.json.

This proves the feasibility of eight simultaneous tones with two shared
chord gains. The probe has no note scheduler, envelope updates or MNC1
decoder. Its code and RAM measurements are not those of a full song player.

The first measured probe used 270 code bytes (Git f07b5c2). The first compact
version used 216 bytes (Git 9e93895); the current 212-byte version saves
58 bytes / 21.5% from the baseline, and improves the measured render cost
from 453 to 442 active cycles. A four-step signed shift/add loop replaces
the unrolled 16-bit multiply; ASR/ROR retain the exact remainder, including
negative inputs. All possible six-note chord sums (-48..42) at levels 0..15
are checked. ADC/RET share the unused interrupt-vector words. The PWM writer
owns Z during synthesis, removing pointer copies, and its midpoint is formed
in the previous-output register. The audit checks every queued output byte
and midpoint as well as the eight-note mix.

Relevant general ideas were reviewed in the local companion project's
z80-tester/docs/Z80-COOKBOOK.md: shared code/continuations, live carry flags,
register reuse and measuring space separately from timing. The AVR loop is
independently implemented and tested; Z80 ROM-stack mechanisms are not used.

The AVR cookbooks were subsequently located in other branches of this same
repository and reviewed directly, without merging unrelated changes:
  codex/speex-avr, 780e64c336452e680793dd76f8a30e4b7cb7ad5b
    docs/avr-asm-cookbook/README.md
  codex/speech-quality, 29d5f2b59fd1ea9a77ba5d477d7a96782003723a
    ATtiny13A/Sound/codec/AVR_ASSEMBLY_RECIPES.md

The general cookbook's invariant-bias/register-reuse recipes apply here:
initialize the two-note sum at -16 and the six-note sum at -48, then add
unsigned EEPROM nibbles. This equals subtracting eight per voice exactly,
and removes one instruction from the inner voice loop. All partial sums
stay in signed-byte range. Retain the reset's 128 constant in r18 while
initializing phases instead of loading it twice. Together these changes
save four code bytes and eight cycles per render, compared with the previous
216-byte probe. The independent mix/PWM checks and exhaustive signed gain
checks still pass. The ATtiny13-specific recipes also confirm the relevant
bounded shift/add, carry-preservation and unused-vector-word techniques.
Hardware-MUL snippets in the ATmega328P cookbook are not used on ATtiny13A.
