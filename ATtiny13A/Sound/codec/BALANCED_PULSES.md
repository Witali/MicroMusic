# Pulse heads with a derived tail

The `mixed-lattice-balanced-v1` PC model stores eight 16-sample heads and
generates the next 16 samples. It keeps the same pitch-triggered excitation,
frame controls, exact integer lattice and output rounding as the pulse model.
This is an experiment toward a complete 1024-byte player, not a qualified one.

Each tail has the opposite signed area to its head. Its baseline is the
integer quotient of that area by 16; the remainder occupies the last tail
samples. Every complete 32-sample form therefore sums to zero, stays inside
the original tap range, and requires no additional fitted tap parameters.
A short pitch period may still truncate the form, as in the existing decoder.
Zero area does not imply zero output DC after the time-varying lattice.

Q1 heads have half-unit resolution and values -7..7. Two signed nibbles per
byte use **64 EEPROM bytes** for eight heads. The optional precomputed signed
tail area descriptors use **eight Flash bytes**. Their range is -112..112.
The PC packer/unpacker rejects the reserved -8 value and inconsistent areas.
These byte counts exclude speech frames, coefficients, alignment and code.

Q2 research uses quarter-unit resolution over the same physical range.
The tail distributes whole Q1 units first, placing a possible finer unit
immediately before the remainder. Thus promoting a Q1 head to Q2 doubles
every integer tap, including the derived tail, and preserves complete PCM.
Q2 heads alone need 80 bytes; the 64-byte storage path is explicitly Q1.

`--tail-policy balance16` explicitly replaces literal tails. The initial
quality is measured again: the conversion can change the sound. Waveform
proposals adjust one head tap and regenerate its tail; all parameter choices
are accepted through the complete integer synthesis and original objective.
No manually corrected phoneme or file-specific tail is used.

```powershell
python tools/fit-mixed-lattice.py --reference web-player/audio/originals/vinni.wav --model ATtiny13A/Sound/research/q4-pulse-shapes/wide32-zero/model.json --output build/balanced-pulses/q1 --tail-policy balance16 --fit-phase --voice-search --step-policy reference --evaluations 24000
python tools/test-mixed-lattice.py
```

The contracts cover every possible head area at both precisions, bounds,
sign symmetry, exact promotion, binary round trips, malformed descriptors,
schema tagging, mutations and retained historical PCM. Quality, AVR tail
generation, full memory and deadlines must be established separately.
