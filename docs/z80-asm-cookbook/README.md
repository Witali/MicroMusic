# Z80 optimization cookbook

## Source-audited ROM/PWM layout examples from LP20

Status: **historical source inspection only**, 2026-11-26. No archived builder,
assembly, emulator or hardware was run in this recovery. The sources and their
provenance are retained in [LP20 history](../../Codecs/LP20/history/README.md).
Preserve original notices; no new license or portability guarantee is assigned.

These examples concern a standalone ROM-threaded LPC/PWM program for a 20 MHz
Z80 tester, not the portable current LPX decoder or an AVR implementation. Early
Spectrum variants use different clocks, port/ULA constraints and sometimes
undocumented instructions. Inspect each builder's actual supported opcode set.
The supplied emulator covers only its stated instruction subset; there is no
compiler ABI to assume for the hand-scheduled direct machine-code emitters.

| Technique | Retained reference | Intended benefit and constraints |
| --- | --- | --- |
| Common terminated-vector tails | Inherited `LP20_v15/LP20_v15/share_tails.py` in v52 sources | Reuse exact record suffixes and pointer-compatible tails to save a specific ROM image. Legal entry points, termination, contextual interpretation and address-space limits must be preserved; this does not itself reduce audio stream bits |
| Use holes in lookup-table pages | Inherited v15/v17 builders under v52 sources | Place immutable vector records only where no legal table access can reach them. Audit every index/range; unused entries for one trained example are not automatically unreachable on general input |
| Pack symmetric PWM width patterns | v51 `compact_lookup.py`, v52 `build_pwm.py` | Store half a symmetric pattern set using nibbles and reconstruct negative widths. Data size excludes the unpack/dispatch program and auxiliary tables; changed dispatch must still meet every output-edge deadline |
| Split high-byte base and small deltas for PCM lookup | v51 `compact_lookup.py` | Compact a finite 10-bit input mapping when each small input group has a provably bounded index increment. Exhaustively verify every legal input against the full mapping; do not infer correctness from only used speech values |
| Share fixed-duration output procedures | v52 `build_pwm.py::actions/split/build` and `test_pwm.cpp` | Trade program duplication for table dispatch. Include dispatch and all instruction paths in per-edge timing. Native sample preview and compressed-codec decoding are separate workloads |

All these are Flash/program-layout techniques for a specified Z80 output
schedule; none establishes a quality improvement for current LPX. The historical
1,024-byte packed-data figure omits executable code and dispatch. The v52 index
player reports 5,027 B total and consumes host-expanded 62.5 kbit/s indices; it
is not the missing full 6 kbit/s LP4V decoder. Supplied results are not new
measurements or evidence with active interrupts, WAIT states or a physical board.

For any new arithmetic port, keep hardware memory/output access separate from
the arithmetic backend, retain an explicitly selectable equivalent C fallback,
and enable assembly only with both supported architecture definitions and a
separate explicit opt-in define. Verify C/assembly output against one reference.
Before claiming a real-time profile, measure the complete playback workload,
output edges and underruns with the actual interrupt configuration active.
