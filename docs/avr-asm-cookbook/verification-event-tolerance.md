# Check verification events against a 10 ns absolute bound

Applies only to the full ATtiny13A `verification` model. The simplified site
model and host profiling have separate requirements. This is acceptance tooling,
with no runtime time-grid, clock-source, peripheral, backend or cache change.

The fixed comparator in
[`avr-verification-events.mjs`](../../web-player/scripts/lib/avr-verification-events.mjs)
requires the verification/device scope explicitly. Its tolerance is 10,000 ps;
callers cannot relax it. Each event keeps its absolute origin. Compare events
by ordinal, preserving every non-time field, count and order exactly. Only the
timestamp difference may be at most 10,000 ps, including the endpoint. Never
align the first observed edge, greedily rematch events or permit an extra 10 ns
of drift at every clock step.

Use uint64 picosecond `bigint` values or canonical decimal strings. JavaScript
Number timestamps can already have lost sub-nanosecond bits at large absolute
times, so the comparator rejects them. Structured state must not use getters,
unsafe integer Numbers or values that lose meaning when compared/serialized.
Failures identify the ordinal/category without printing supplied event values.

[`verify-virtual-event-accuracy.mjs`](../../web-player/scripts/verify-virtual-event-accuracy.mjs)
uses the real generated CPU/native device with the conservative verification
policy. Its independent references come from source-period arithmetic and the
manufacturer's documented counting/instruction rules:

- Clock checkpoints project the ideal rational timestamp as
  `floor(halfCycles * 10^12 / (2 * frequencyHz))`. Irregular large spans expose
  accumulated rounding errors that short per-step comparisons would miss.
- [ATtiny13A DS40002307A, sections 11.5 and 11.7.2](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
  specify delayed compare flags and the CTC period `1 + OCR0A`. The fixture
  starts from reset TCNT0=0 without a TCNT write/compare block and checks every
  counter/flag checkpoint plus OC0A toggle at each complete period. CTC TOP=0
  is WGM2; it does not resolve the open phase-correct WGM5 TOP=0 case.
- [AVR instruction manual DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
  gives one cycle for LDI/OUT and two for RJMP, with SREG unchanged. The small
  firmware sets DDR at cycle 2, raises PB0 at `4 + 4n` and lowers it at `5 + 4n`.
  It checks actual instruction retirement/registers, absolute output timestamps
  and identical final architecture under whole/partitioned execution.
- A declared ideal 20 MHz external CLKI waveform checks PB3 edges at absolute
  25 ns intervals and actual CPU progress. ATtiny13A has no CKOUT pin/fuse;
  internal clock checkpoints are not presented as a physical CLKOUT trace.
- Input transitions one picosecond apart beyond `2^53` ps remain distinct while
  RESET is held. Every driven-mask snapshot retains RESET low; replacing it
  with a PB0-only snapshot would release RESET and change the experiment.

The original manufacturer PDFs, register definitions and SDK are already pinned
in the project's download/build registries. No new document or tool download is
needed for this technique.

These are explicit digital/clock profiles with selected frequencies and zero
startup fixture. Their floor-projected reference has sub-picosecond projection
uncertainty; it is not a measured RC calibration curve or a physical electrical
delay oracle. Software agreement cannot close unresolved silicon behavior,
instrument uncertainty or a hardware accuracy requirement for all peripherals.
The [integration report](../../web-player/reports/virtual-event-accuracy-20261027.md)
records every fixture's event count, maximum error and trace/source hashes.
