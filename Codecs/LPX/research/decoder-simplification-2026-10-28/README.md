# Exact decoder simplification: measured combined result

The v5-only decoder is smaller and faster with **identical decoded sound**.
Starting from `3f717df5`, six small source changes exploit format bounds,
quantization and state lifetime. No new format, approximation or assembly is
introduced. Existing common-format support and explicitly selectable C fallback
remain available.

| Measured complete-image workload | Full Flash saving | Static SRAM saving |
| --- | ---: | ---: |
|101 single-segment selected images |110 B each |1 B each |
|10 selected multi-segment chains |246 B each |1 B each |

Non-stream program Flash, including startup, runtime, lookup/switch tables and
retained IRQ/profiling harness, is **5085-5336 ->4975-5090 B**. Exact embedded
streams are unchanged. Full Flash is linked `.text+.data`; the saving is actual
before/after image cost, not a sum of source or table byte estimates. No
profiling symbols or measurement code were removed to obtain it.

## Applied simplifications

- **Bounded subtraction:** compare the declared payload with `size-22` after
  checking the actual span. This removes an untrusted wide addition without
  changing read order, overflow rejection or error precedence.
- **Narrow spectrum arithmetic:** valid and rejected Rice proposals fit signed8
  before validation (profile6 range-64..127). Keep sticky-error and order/range
  checks, then widen only for the centered LSF representation.
- **One format byte:** compact-only stores its validated profile and optional
  excitation flag together. The common representation stays unchanged.
- **Exact cosine grid:** centered v5 LSFs and LPC segments1/2 reach only even
  cosine nodes with zero fraction. A130 B direct table plus a small lookup beats
  both the previous88 B compressed representation and an80 B alternative on total
  linked Flash. Common and segments4 retain generic interpolation.
- **Known unit product:** a polynomial factor's trailing coefficient is always
  +/-4096, so that rounded product is exactly+/-c. Other product floors, the
  wide multiply path and final LPC clamp remain intact.
- **State lifetime:** skip copying ten LSF words in the second160-sample packet
  half, whose LPC endpoint is already cached. Refresh the previous spectrum
  before the next transmitted first-half spectrum; partial/error/copy semantics
  are checked explicitly.

Isolated contributions are not additive under LTO. Standalone parser work saved
24-38 B plus1SRAM; cosine56 B; copy scheduling14 B on single streams or152 B on
measured chains; the unit product was size-neutral or2 B smaller. The combined
result above was recompiled and simulated independently for every selected
image. [Systematic methods catalogue](../../../../docs/avr-asm-cookbook/lpx-decode-simplification.md).

## Timing, configuration and correctness

ATmega328P / AVR5 GNU ABI, AVR-GCC 7.3.0, explicit ASM,16 MHz / 8 kHz,
queue 512/prefill 384, default LPC segments2, unroll 1/tuning 0 and
`-Os -flto -mcall-prologues -mrelax`. Source/headers/toolchain/flags and
[all paired observations](rows.json) are pinned in [the summary](summary.json).

All 111 normal selected chains plus five+100-cycle IRQ controls were freshly
simulated. Every complete output equals both independent-model PWM and frozen
baseline PWM; counts match, with zero underruns and decoder errors. Minimum
observed queue occupancy before producer EOF is386 and after-ready stack margin
rises882->891 B. No physical board, analog output or universal/startup worst-case
claim is made.

Across 4,914,100 profiled normal samples, IRQ-inclusive decode cycles/sample fall
**826.154384 ->782.715071 (-5.258%)**; each normal image improves4.694-7.044%.
The existing runner stores at most 64000 decode durations:104 images have complete
duration coverage and 12 long controls report only their initial window. Full
PWM/playback/underrun checks cover the entire chain in all 116. These coverage
labels remain explicit per row; partial duration totals are not full-recording
averages. Static SRAM is1084-1085 B after the one-byte format-state saving.

Four common-layout image pairs save18 B(single) or24 B(five segments), with
unchanged SRAM. This is [cost-only evidence](common-layout-costs.json), not a
new common-layout AVR timing admission.

Host validation on the final combined source:

- 55 focused tests, including generic4096-point cosine/frozen34816 LPC output,
  exact grid/reflection/segments1/2/4, bandwidth expansion, snapshots, parser
  lifecycle and unit products. New compiled parser probes cover 7,355,956 cases;
  compiled polynomial recurrence checks cover564,288 factors.
- All 181 frozen corpus cases /306 segments /1224 baseline+selected streams match
  common/v5-only native decoders, the integer model and frozen PCM16/PWM.
  [Receipt](compatibility.json).
- An independent current-selected audit covers 204 baseline/anchor/default/proxy
  chains,244 distinct streams and976 native PCM/PWM comparisons. All original-
  level metrics remain exactly unchanged. [Receipt](current-selected-audit.json),
  [audit source](audit_selected.py).
- ASan/UBSan passes 605670 mutation/reset cases per layout (1211340 total), zero
  sample-cap exhaustion and exact resets. Full source/model/fuzzer inventories
  stayed unchanged. [Receipts](sanitizers.json).

## Rejected or deferred approaches

Keep the negative evidence so the same attractive identities are not repeatedly
reintroduced:

| Experiment | Measured result | Decision |
| --- | --- | --- |
|Half reciprocal P polynomial |+70..160 B Flash, up to24 B scratch saving |Reject for current Flash priority |
|Mirror full P array after half work |+88..90 B, no RAM benefit |Reject |
|80 B differential cosine table |34 B image saving, versus56 B direct |Choose direct table |
|Branchless signed nibble |+38 B short /+6 B long |Reject |
|Compact position recheck removal |+146 B short /-102 B long |Reject as a uniform size choice |
|Branchless Rice zigzag |+124 B short /-156 B long |Reject as a uniform size choice |
|Bounded optional-pulse insertion |+26 B single /-124 B long; byte form+144/-110 B |Reject as a uniform size choice |

These branch-dependent reversals include real LTO/inlining effects; algebraic
simplicity alone does not establish a firmware saving. Q polynomial
antisymmetry also fails under signed floor rounding and must not be used as an
exact identity. Valid clustered spectra still require the wide multiplication
path and final clamp.

[Parser measurements/protocol/patches](parser/PROTOCOL.md),
[polynomial evidence](../decoder-polynomial-2026-10-28/README.md),
[grid evidence](../v5-grid-cosine-2026-10-28/README.md),
[copy scheduling evidence](../v5-half-spectrum-2026-10-28/README.md).
Byte LSF storage and packing the half/subframe phase remain explicit future
experiments; neither is silently enabled.

## Reproduce and use

Use the existing core tests with tools/tests on PYTHONPATH and a native g++.
The exact AVR recipe/collector is documented in
[SPEECH_FLASH.md](../../01_ACTIVE_Q0_CODEC/tools/SPEECH_FLASH.md). Keep feature
settings identical across the class and all consumers. Arithmetic defaults to C;
ASM still requires the separate enable define and real supported target macros.
The C fallback remains numerically checked; its earlier inability to meet8kHz
on this AVR recipe is not overturned by ASM-only timing.

The immutable111+5 input inventory comes from the preceding
[joint-search/full-budget study](../v5-joint-budget-2026-10-28/README.md).
Reproducing exact corpus measurements requires its local private media/streams;
public source hashes cannot recreate them. Original levels, complete joins and
encoded bytes were preserved. Existing audio comparisons remain valid because
new decoding is bit-exact.

Only anonymous numeric results and public source/toolchain fingerprints are
retained here. Per-media PCM/PWM/stream/ELF/binary fingerprints, names, path-bearing
manifests, media, generated firmware and logs stay in ignored storage. Tested
source bytes are identical to the published source despite a metadata-only
cleanup of unpublished research receipts before publication.
