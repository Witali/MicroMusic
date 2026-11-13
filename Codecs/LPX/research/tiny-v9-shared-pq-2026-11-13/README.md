# Share the Tiny88 LPX v9 polynomial loop

Baseline `c391ad09`. ATtiny88 / AVR25 without hardware MUL, AVR-GCC 7.3.0
with the GNU AVR ABI, `-Os -flto`, SRAM512, two LPC segments, MUL16 unroll 2
and FIFO32/prefill24. simavr 1.6 runs at 16 MHz with an 8 kHz sample rate.
Program Flash includes the player and tables and excludes the embedded LPX
payload, which is identical in each before/after pair.

P and Q initialize the first two operands for one descending loop. P's
symmetry makes both operands equal to its old middle coefficient. Q's
trailing coefficient stays at −4096 for every factor, so the first
iteration uses that constant. The adjacent coefficient is the old
penultimate coefficient minus the current cosine factor. All interior
products go through the existing Q12 arithmetic and preserve its two
separate floors in the wide case.

The converter stores six words for P and eleven for Q. The aligned
workspace spans 68 bytes with up to three bytes of lead-in, within the
111 dead future pitch-ring slots. Offsets wrap modulo 256 before loading
or storing each aligned 32-bit word. The C backend remains selectable
with `LPX4_ENABLE_ASM=0`.

| Measurement | Baseline | Shared loop |
| --- | ---: | ---: |
| `convertLsfAt`, bytes | 1166 | 1076 |
| Program Flash, bytes | 5360–5361 | 5270–5271 |
| Highest mean with IRQ, cycles per sample | 1664.87 | 1664.36 |
| Peak stack, bytes | 56 | 60 |
| Minimum queue depth, samples | 23 | 23 |

All 308,339 PWM bytes across 22 loads match. The 38-cycle IRQ, EOF and
queue drain checks pass with zero underruns. Twenty-one loads are faster
by 0.12–0.51 cycles per sample on the active CPU plus IRQ mean and one ties
at the reported precision. Peak active decoder CPU time per call drops
by 83 cycles in all 22 loads. Minimum observed stack margin is 18 bytes.
All 18 WebUI images rebuild byte for byte. An independent full-convolution
oracle with UBSan checks 368,640 conversions across all 256 ring cursors
and confirms all 145 live history bytes are preserved. That oracle selects
the shared C++ loop in a private copy with portable C products. The 22
simavr runs use the actual AVR25 assembly arithmetic.
[Per-load results](measurements.json).

Moving both polynomial work areas to physically contiguous spans reduced
Flash by 46 B on four control loads but increased the mean by up to 10.06
cycles per sample. Keeping two old coefficients live in the wrapped
loop saved 76 B and increased the mean by up to 0.105 cycles per sample.

Reproduce the paired run from the repository root with AVR-GCC, g++ and
simavr 1.6. The command allows the measured four-byte stack increase and
still checks the 512-byte SRAM limit. On Linux omit `--wsl Ubuntu`.

```powershell
python Codecs/LPX/01_ACTIVE_Q0_CODEC/tests/verify_lsf_compaction.py build/pq-matched --target tiny --baseline c391ad09 --max-stack-growth 4 --wsl Ubuntu
```
