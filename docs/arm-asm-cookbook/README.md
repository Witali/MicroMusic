# Arm arithmetic and timing notes

## Cortex-M0: budget a Codec2 port before predicting its runtime

Status: **analysis only; no Arm binary, board timing or real-time support**.
Target considered: Cortex-M0 /Armv6-M at a hypothetical 75 MHz. This is not
a qualification of any manufacturer's MCU, memory interface or clock setting.
No Arm ABI, compiler/options or assembly backend has been tested here.

Primary references:

- Arm Cortex-M0 Technical Reference Manual, DDI 0432C,
  [instruction summary and zero-wait-state cycle counts](https://support.arm.com/documentation/ddi0432/c/programmers-model/instruction-set-summary?lang=en).
- Arm's [Cortex-M comparison](https://developer.arm.com/Additional%20Resources/Compare%20IP%20for%20Cortex-A%20premium%20CPUs)
  lists no floating-point hardware for M0/M0+.

M0 has native 32-bit integer arithmetic, but `MULS` returns only the low
32 bits. Its latency is either 1 or 32 cycles depending on the configured
implementation. A 32x32 product needing all 64 bits therefore cannot be
replaced with a single low-word MULS. This matters to the Codec2 Q30/Q22
products and Q60 cosine. Remaining floating-point work needs software
routines. Flash wait states and library/compiler choices also affect runtime;
the core's zero-wait-state instruction table does not settle MCU performance.

The completed [AVR matrix profile](../../Codecs/Codec2/MATRIX_SPECTRUM_RU.md)
measures 218 EN +147 RU frames, weighted mean **14,021,055 AVR cycles**.
The independent extreme sequence has maximum **29,508,800 AVR cycles**.
These are ATmega64A /AVR-GCC 7.3.0 `-Os` /avr8js 0.21.1 measurements,
not Arm cycle counts. The workload is Codec2 3200, 160 PCM samples at
8 kHz per 8-byte packet, giving 20 ms of audio per frame.

At 75 MHz, 20 ms permits **1,500,000 core cycles**, before interrupts and I/O.
Relative to the measured AVR counts, the port must reduce cycles about
**9.35x on average**; meeting a strict 20-ms deadline on the heaviest tested
frame would require about **19.67x**. The ratio is not an architecture claim.
If r is an assumed ratio AVR cycles /Arm cycles, the scenario is
`time_ms = AVR_cycles / (r * 75000)`:

| Assumed cycle reduction r | Ordinary-frame mean | Tested extreme maximum |
| --- | ---: | ---: |
| 4x | 46.74 ms | 98.36 ms |
| 8x | 23.37 ms | 49.18 ms |
| 12x | 15.58 ms | 32.79 ms |

None of these r values is measured or predicted as the actual M0 result.
The table explains the required improvement without treating MHz as a
cross-architecture benchmark. A queue can absorb isolated long frames only
if sustained throughput and the latency/memory budget allow it.

Next qualification: choose an actual MCU and vendor headers, pin a toolchain,
compile the selectable portable C arithmetic without faking target macros,
verify the same full PCM/RNG corpus and conditioning holdout, then measure
the linked binary with actual memory wait states. Finally measure stack,
interrupt output timing and underruns before claiming real-time support.

A separate [LPC-postfilter-off experiment](../../Codecs/Codec2/NOPOST_RU.md)
now reduces AVR mean EN/RU costs to about 9 million cycles, but makes four
extreme frames slower. Its timbre change is unqualified. Neither the roughly
36% AVR average gain nor its new cycle counts are an Arm timing measurement;
compare both profiles on the actual MCU before selecting one.
