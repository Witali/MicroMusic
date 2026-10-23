# First measured COREOPT -> DATAOPT cycles

The hard target remains **STOI>=.90 and spectrogram_loss<=.344975554**, with
1024B Flash and64B EEPROM on the unchanged22272-sample Vinni reference.
Two measured core compactions and deterministic data passes were completed.
**Neither cycle achieves the requested joint quality target.**

The compact assembly change saves16B in each numerical profile without changing
its byte arithmetic or decoded PCM. Its separate tests checked old/new PCM,
the four full-capacity images and actual multiplications in three engines.
The cyclic driver accepted only matching successful build reports/binary hashes,
then ran2000 deterministic objective evaluations per DATAOPT pass. Frozen
initial6000-proposal sources and results were not modified.

| Cycle / compile profile | Old -> new code B | Actual capacity B | DATAOPT stream B | Actual final Flash/EEPROM B | Final STOI | Final eSTOI | Final spectrum |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1, base floor | 408 ->392 | 615 ->631 | 591 ->600 | 994 /64 | .846204 | .659204 | .493203 |
| 2, pole floor | 430 ->414 | 593 ->609 | 600 ->608 | 1024 /64 | .847509 | .659771 | .493654 |

Cycle1 starts from the saved highest-quality clean seed with STOI.842286 and
spectrum.497696. With the same591B data, COREOPT changes the packed memory
requirement1000B ->984B; DATAOPT uses additional descriptions and finishes at
994B after EOF/alignment. Cycle2 continues from the improved600B data.
That data would require1032B with the older430B pole core and is explicitly
infeasible there; the compact414B core reduces the requirement to1016B.
Further data fitting increases the stream to608B and the final image to1024B.
The additional -15/16 pole mapping is a separately tagged format; only the
compaction within a profile is asserted to preserve numerical semantics.

All eight coordinate families were evaluated: table entries, paired row-sum
edits, pitch, gain, modes, whole-half-run coefficients, individual-frame
coefficients and duration transfers. Cycle1 accepted40 moves; cycle2 accepted22.
The measured gains in these passes came from frame/coefficients/timing rather
than accepted pulse-table changes. All proposed actual streams were byte-sized
before their capacity check. Every source sample was retained.

The scalar improves modestly, but the requested spectrum reduction is absent.
The final raw output mean also remains positive,.0772–.0776 versus the original
approximately-.000059; no hidden DC or gain correction was applied. Standard
STOI and the frozen spectrogram objective's high-pass/RMS policy are retained.
These measurements do not establish a satisfactory natural voice or prove that
the format cannot improve further.

## Subsequent actual candidate qualification

Both fitted outputs were assembled and run in all three engines after DATAOPT:

- Cycle1: actual994B Flash/64B EEPROM;66816 output samples exact; minimum
  deadline slack330 cycles; no lost/missed events or arithmetic wraps.
- Cycle2: actual1024B Flash/64B EEPROM;66816 output samples exact; minimum
  slack299 cycles; no lost/missed events or arithmetic wraps.

66816 includes the full22272-sample phrase plus2N midpoint silence. Physical
hardware testing is not claimed. Raw DATAOPT captures conservatively say the
new candidate was not yet qualified at capture time; `qualification.json` and
each subsequent `cycle-NN/avr/build.json` record the later successful builds.

## Artifacts and reproduction

`vinni/report.json` and `cycle-NN/cycle.json` contain core evidence, before/after
quality/memory, each accepted coordinate and the explicit target failure.
`before/`, `after/`, `pareto/NN/` retain model/table parameters, actual compressed
speech and measured quality. Raw EEPROM/WAV/PCM and compiled images remain in
ignored `build/q3-core-data-cycles/vinni/`. All64 EEPROM values are present in
each model JSON; no speech prefix shares those bytes.

The original reference SHA is
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
Core code provenance is the compact profile commit `7e276c2`; the cyclic driver
is commit `69a36ef`. Exact source hashes and compiled-image hashes are retained.
Use `tools/probe-q3-pulsebook-cycles.py` with the recorded initial model/core
reports and default2000 evaluations; `codec/Q3_CORE_DATA_CYCLES.md` documents
the API. Five focused tests pass. Public firmware remains unchanged.
