# LPX RAM reuse: measured alternatives for a 512-byte SRAM profile

Four exact storage proposals were investigated for the intended ATtiny88 / 16 MHz
port. None passed the initial absolute no-slowdown requirement. The user then
authorized the smallest practical slowdown and requested a separate profile for
ATtiny88 or comparable 512-byte SRAM devices. **The selected approach is the
96-byte dead-ring reuse**, retained separately on `codex/lpx-sram512-profile`.
The standard decoder remains unchanged. The alternatives below record the
original experiments; they are not themselves installed by this report.

| Proposal | Persistent RAM saved | Matched timing result | Decision |
| --- | ---: | --- | --- |
| Pitch history 256 -> 145 | 111 B | AVR5 C +1.07..1.09%; ASM +1.43..1.58% mean cycles | Reject |
| Sequential P/Q, split full P across dead coefficients/new anchor | 48 B | AVR25 C: P4 +0.001499%; P6 -0.001689% | Reject: P4 slows |
| Union of working LPC coefficients and Q polynomial | 20 B | AVR25 C: both means and worst output gaps increase | Reject |
| Both polynomials in the dead part of the 256-byte pitch ring | 96 B | AVR5 C +0.10..0.14%; ASM +0.79..0.85% mean cycles | Select for separate `sram512` profile |

The 48-byte proposal has the smallest isolated slowdown, but leaves too little
room on a 512-byte device: its 446-byte decoder plus the observed 54-byte stack
already uses 500 bytes before player state, a queue or an ISR. The 20-byte union
does not fit even that unpaced budget. Dead-ring reuse leaves a 398-byte decoder;
the measured probe uses 403 bytes including five observation bytes plus a
54-byte observed stack, leaving 55 bytes. That is a more useful starting point
for small-buffer/ISR work, but is not a complete playback memory admission.
The 111-byte history option saves slightly more RAM with a larger speed cost.

The first, sequential and union experiments use the earlier 1,008/1,501-byte
profile-4/profile-6 pair. The ring experiment uses the published 1,008/1,899-byte
pair. Both pairs contain 19,200 samples per stream, but their profile-6 bytes
are different. Results across those pairs are not direct comparisons.

## What can and cannot share storage

The pitch predictor only needs the preceding 145 excitation codes. Reducing its
allocation adds wrapping work to the sample path. The compile-time proposal
accepts 145..256 only in the v5-only layout; 145 is inclusive and must read the
old slot before overwriting it. Default-256 firmware was byte-identical to the
pre-proposal firmware in the two measured ATtiny88 probes.

Working `a_[10]` coefficients are dead during an LPC anchor conversion and are
fully refreshed before synthesis resumes. The new anchor is also dead before
conversion. The sequential proposal preserves all ten **32-bit** P coefficients
as high/low halves in these two 20-byte regions while reusing one 48-byte
polynomial workspace. It never truncates or clamps P before adding Q. The union
proposal instead shares `a_` with Q and preserves the original arithmetic loop.
Both require the output anchor to be disjoint from `a_`, as all actual callers
are. Moving the polynomial arrays to the stack would not save peak RAM.

The original 256-byte pitch ring has 111 circular slots ahead of its write
cursor that are dead until new samples overwrite them. The last proposal uses
96 of those bytes for the two polynomials. Aligned four-byte accesses use
`memcpy`, so no unaligned typed access or conflicting object lifetime is needed.
Native checks covered both published clips and changing/static/clustered spectra,
optional excitation and LPC segment counts 1/2/4: 84 PCM16/PWM comparisons passed.
This reuse preserves sample arithmetic but still costs conversion cycles.

Filter history, the previous LPC anchor, and spectra needed for interpolation or
future delta decoding remain live. They cannot be overlaid merely because they
are not accessed by every instruction. Copy/assignment and restart must also
preserve any live state.

## Measurement scope

[`measurements.json`](measurements.json) retains 16 anonymous full-image rows:
eight history comparisons and eight ring comparisons. ATmega328P / AVR5,
AVR-GCC 7.3.0, 16 MHz / 8 kHz, LPC segments 2, explicit C/ASM selection,
unroll 1 / tuning 0, `-Os -flto -mcall-prologues -mrelax`, FIFO 512 / prefill 384,
and the normal active audio ISR were held fixed. Every full 19,200-sample PWM
output matches native output. Duration counters cover the complete stream.
All admitted ASM images have zero underruns; C misses the 8 kHz deadline.
Every ring candidate also increases the maximum rolling 160-call duration.

The sequential/union comparisons executed actual AVR25 instructions in the
existing transpiled CPU at 16 MHz, without interrupts. The smaller 145-history
probe has 388 B static RAM including five observation bytes and uses 55 B of
observed stack. Its 6,150..6,431 cycles/sample already exceed the 2,000-cycle
8 kHz budget. The ring probe has 403 B static RAM and 54 B observed stack.
These exclude playback queues/ISR stack and do not establish real-time support
or physical-board behavior. ATtiny88 has no hardware MUL and cannot select the
AVR5 multiplication backend.

## Independent C speed result

Splitting a signed 32-bit shift into high-word scaling and low-word extraction
preserved all tested integer outputs. In the matched AVR5 **C** pair, it reduced
mean cycles 17.5..18.7%, while adding 182 B complete Flash and three observed
stack bytes. The original inline-assembly statements were unchanged. Native
checks included full-range boundary/random shifts, exhaustive PWM gain pairs
and UBSan. C still missed the 8 kHz deadline.

Combining these shifts with 145-history/sequential storage saved 159 B and was
faster than the original C baseline, but was 1.05..1.12% slower than the improved
256-history C baseline. That does not satisfy the memory component's strict
no-slowdown rule. Under the later relaxed criterion, the selected dead-ring
profile still has a smaller isolated memory cost in cycles. The shift patch is
also a private-stage proposal: production
would need an explicit selectable flag, unchanged non-AVR defaults, and fresh
source-bound admission. It is not installed by this report.

## Reproduction and retained alternatives

The unchanged production source base is `2e482949` (its LPX core is identical
to `f1bd64e6`). Use an isolated checkout of that base.
[`alternatives/pitch-history.patch`](alternatives/pitch-history.patch)
contains the rejected compile-option implementation. Its synthetic validator is
[`reproduction/validate_pitch_history.py`](reproduction/validate_pitch_history.py);
set `LPX4_HISTORY_SOURCE` to the patched `01_ACTIVE_Q0_CODEC` directory and put a
native `g++` on PATH. Optional stream paths use `LPX4_PITCH_HISTORY_FIXTURES` as a
JSON list. This validator requires no private recordings for its synthetic cases.

The other workspace patches are relative to `01_ACTIVE_Q0_CODEC` and were measured
on copied sources after the history patch. Keep history 145 for sequential/union,
256 for ring scratch. Do not combine their layouts. Exact per-image media,
PWM/ELF fingerprints, compiler/runtime bindings, failed host attempts and logs
remain in ignored local receipts. No raw media or artifact fingerprints are
exported here.

Next work must preserve the measured baseline and explicit speed cost, measure
a complete 512-byte RAM budget including stack/ISR/queue, and admit actual
firmware before exposing a Micronucleus download or claiming ATtiny88 playback.
