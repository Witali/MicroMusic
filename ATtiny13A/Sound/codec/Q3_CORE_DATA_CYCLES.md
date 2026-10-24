# Verified COREOPT -> deterministic DATAOPT cycles

`tools/probe-q3-pulsebook-cycles.py` records each measured assembler-core
capacity before fitting the data. A COREOPT input must be a successful actual
three-engine build report and its matching compiled image. The driver checks
code/stream/EOF/alignment/EEPROM consistency, rounding and coefficient mapping.
Claims of unassembled or merely estimated code savings cannot enter the cycle.
The assembler optimization itself is the separately reviewed compact-core
change; this driver consumes its measured result and automates DATAOPT.

```powershell
python tools/probe-q3-pulsebook-cycles.py --reference original7500.wav `
  --model saved-model.json --core-report verified-compact/build.json `
  --previous-core-report verified-previous/build.json `
  --output build/q3-core-data-cycles/example --max-evaluations 2000
python tools/test-q3-core-data-cycles.py
```

Repeat `--core-report` to execute successive measured profiles and repeat
`--model` for saved seed/frontier candidates. Product rounding must match the
seed. Packed nibble0 from the distinct -15/16 pole format cannot be silently
fed to the ordinary Q3 profile. The frozen initial random-search tool and both
numerical oracles remain unchanged.

## Deterministic coordinate pass API

```python
state, pareto_states, report = coordinate_sweep(
    objective, state, budget, max_evaluations=2000, branch='balanced')
```

The objective/state API is the frozen `probe-q3-pulsebook.py` API. Parameter
families are deterministically interleaved so a bounded pass sees each family:

- all64 source-table entries +/-1;
- adjacent/cyclic source-entry pairs with opposite changes, preserving row sum;
- frame pitch +/-1/2, gain +/-1 and every source mode;
- coefficient nibbles +/-1 across a whole shared half-run;
- individual-frame coefficient moves, allowing measured newly freed bytes to
  describe an additional change instead of forcing all frames to share it;
- +/-64-sample transfers between adjacent durations, preserving every sample.

Every proposed stream is actually packed before its capacity check. All
existing byte-wrap, peak, sample-step and full-duration guards still apply.
No source/DC/gain postprocessing is introduced. Source-row sums are not forced
to zero; paired edits preserve the current sum and raw mean/RMS remain visible.

`balanced` greedily improves spectrum+6*max(0,.90-STOI); `spectrum` or `stoi`
greedily improves that coordinate. Another metric may worsen, so the complete
non-dominated frontier remains explicit. There is no old baseline quality
ceiling or hidden previous-STOI floor. The target is always the joint test
STOI>=.90 and spectrogram_loss<=.344975554.

The maximum applies to actual objective evaluations; duplicate/unchanged and
over-budget proposals are counted separately. The pass is finite and contains
no random proposals. It records accepted coordinates and before/after metrics.
For the next profile, only the balanced/STOI/spectral representatives need to
be rescored; all Pareto parameters are still exported for review and resumption.

## Memory, quality and qualification records

Each `cycle-NN/cycle.json` records:

1. COREOPT old/new code capacity, evidence hashes and unchanged numerical
   semantics, with memory before and after replacing the core.
2. DATAOPT initial/final quality, actual packed bytes, evaluated/accepted
   parameter families and before/after memory including EOF and alignment.
3. Explicit target pass/failure; no new quality claim is inferred from space.

`before/`, `after/` and `pareto/NN/` contain complete models and streams.
The DATAOPT report marks the new parameters unqualified until their separate
compact-builder run completes. The initial retained study also includes those
subsequent actual `avr/build.json` qualification reports, where all three
engines reproduced each22272-sample phrase and its2N midpoint-silence tail.
Hardware testing is distinct from emulator verification and is not claimed.

Five tests cover paired row-sum preservation, shared-half/duration structure,
deterministic bounded improvement, a real two-byte expansion enabling a formerly
infeasible stream edit, and rejection of inconsistent capacity/missing engines
or changed compiled-image evidence. First real results are in
`../research/q3-core-data-cycles/README.md`; the hard quality target remains unmet.
