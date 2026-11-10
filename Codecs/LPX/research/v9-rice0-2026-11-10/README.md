# Experimental lossless delta Rice0

This is a **research format, not admitted to the production firmware**. The
active universal decoder, normal `speech_v9.py` conversions and web images stay
unchanged. Program growth and small timing regressions in the screens below
prevent promotion under the requested no-regression conditions. This experiment
does not improve the audible rasp: every decoded sample is deliberately exact.

## Wire change and selection

V9 flag64 selects Rice-k0 for delta LSF vectors. Old six-bit P6/sparse80 uses
k1 for deltas; five-bit P4 already uses k0. Gap k remains `bits-4`; repeat syntax,
the eight-zero literal escape and all non-spectral fields stay unchanged.
The reader accepts a redundant flag64 on P4, but the writer never adds it there.
The actual LPC, pitch, scale and filter parameters stay in the stream.

The explicit `tools/speech_v9_rice0_experiment.py --optimize-rice0` experiment
chooses the shortest gap/delta form per changed vector, and sets64 only if the
**complete file** becomes strictly smaller. Ties, growth and noncanonical old
syntax retain exact original bytes. Converting back to legacy5/8 clears64 and
re-encodes spectra with the old width-dependent k; copying new Rice bits into a
legacy container would be incorrect. Normal conversions never opt in.

[Counts](counts.json): 318 files (306 corpus segments and 12 public controls),
410,968 -> 391,017 bytes, saving **19,951 bytes / 4.8546%**. There are 271 smaller
files and 47 exact-old fallbacks; none grows. Most savings are in music and
instruments; Chego stays 297 bytes. This is not a majority speech-quality result.
The corpus excludes retained private media, media hashes, names and locations.
The [isolated-tool comparison](tooling-comparison.json) verifies every one of
the 318 selections against the saved study output, exact old-syntax roundtrips,
unchanged default conversions/statistics, legacy conversion and idempotence.
It binds the experimental tool and its seven stdlib tests to their code hashes.

## Equivalent C reference and validation

`reader.py` makes a private source tree from production `95346ea9`. It verifies
the original core hash, applies only the v9 flag mask and delta-k selection, and
verifies the resulting core hash. It **retains** the compact error check. C is
the default backend; the existing architecture checks and explicit ASM-enable
define still govern assembly. Memory access is independent of backend choice.

[Native proof](native.json): all 318 streams, 15,371,791 samples and 12,084 complete
decodes pass. Eight C variants cover standard/SRAM512 memory, ROM pointer0/1,
batched remaining-count 0/1, ROM/callback input and PCM16/PWM8 output. Every
selected stream exactly matches the unchanged production-C baseline; 18 saved
ordinary-v5 C controls also match. EOF, error, count and callback bounds pass.
[Frozen source digests](native-sources.json) record both raw and normalized-LF
hashes; raw CRLF hashes differ from generated LF copies without changing code.
Host object sizes in the proof are not AVR SRAM measurements.

Three retained native tests additionally cover deterministic profile 4/6/15
fixtures, every boundary around subframes, maximum 64000 count, input switching,
signed delta escapes, forced zero deltas, redundant P4 flags and corrupt tails.
They compile the prototype in private temporary storage, leaving production
sources unchanged. All ten stdlib/native tests pass:

```sh
python3 -m unittest discover -s Codecs/LPX/01_ACTIVE_Q0_CODEC/tests \
  -p 'test_speech_v9_rice0*.py'
```

## Limited runtime screens, not admission

At 16 MHz/8 kHz, AVR-GCC 7.3.0 -Os/LTO, FIFO 32/prefill 24 and explicit AVR25 ASM,
the original no-trim prototype occupies 5619 program bytes, +4.365% against the
former 5384-byte decoder. One old-syntax Chego screen measures 1547.369736 total
mean cycles/sample (active decoder CPU + complete IRQ), stack 67 and margin 11 bytes;
its PWM is exact and has no underruns. This is **not** an all-profile IRQ
admission of flag64 or a claim that 1500 cycles/sample was reached.

A private combined error-check removal shrinks this to 5611 bytes and improves
that particular Chego screen, but error-check removal separately slows
bread-low15. A different logical expression for k also regresses old examples.
Neither combined candidate is selected. Production timing/size receipts remain
bound to their original sources; none is retagged as a new measurement.
