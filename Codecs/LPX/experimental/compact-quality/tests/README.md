# P3 canonical coefficient-crop regression

These independent native tests reach the private `localCoefficients` helper by
including `LpxLpcRefine.cpp` in one test translation unit. The runner omits its
ordinary compilation unit, adds no public API, and reuses the production native
source list and portable arithmetic defines. Historical/downloaded code is not
executed. Generated binaries and source/hash receipts stay under ignored
`build/compact-quality/`.

`local_trace.cpp` checks the cropped coefficients against the complete trial's
`coefficientTrace`, then checks forward audio against the serialized complete
stream decoded by `Lpx4HybridCore`, including PCM, PWM and exact EOF. The native
decoder supplies an independent synthesis/packing oracle rather than another
call to the helper under test. Tests cover:

- P3 raw edits that quantize away, and source-order temporal dead zones that
  propagate into later unedited frames. The helper must canonicalize the whole
  trial before selecting its interpolation context.
- Reset/start-zero and nonzero run starts, 8/12/16 kHz, tails at 1/19/20/21,
  39/40/41, 159/160/161, 319/320/321, 641 and 1601 samples.
- P4/P6/P8 controls with unchanged ordinary coefficient semantics.
- Genuine continuation after a 1280-sample prefix, with its actual synthesis
  histories, previous spectrum and analysis context; the whole serialized file
  is decoded and compared with the carried suffix. Isolated `verifyStream`
  reset checking is not used as continuation proof.
- Bounded/deterministic LPC-run proposals, exact complete-file caps, no
  serialized no-op finalist, legal P4/P6 pulses and preserved unrelated metadata.
  These LPC proposals intentionally may change spectra and permitted pulses;
  this is not a claim that every proposal has the same size as its incumbent.

The perfect-PCM target check explicitly selects PCM scoring. With PWM scoring,
an exact PCM reconstruction can still have static duty-grid error; returning a
different raw proposal is therefore not intrinsically a defect.

Run in Linux with g++, or from Windows with the installed WSL toolchain:

```powershell
$env:LPX_TEST_WSL='Ubuntu'
python Codecs/LPX/experimental/compact-quality/tests/test_local_trace.py
```

For the before/after proof, save the exact baseline `LpxLpcRefine.cpp` into
`build/compact-quality/pre-fix/LpxLpcRefine.cpp` with `git show` bytes from
`e467dc9e`, then run:

```powershell
python Codecs/LPX/experimental/compact-quality/tests/test_local_trace.py --source build/compact-quality/pre-fix/LpxLpcRefine.cpp --expect-pre-fix
```

The pre-fix option requires the specific regression exit30 and diagnostic in
both P3 and continuation groups. Generic crashes, invalid fixtures, control
failures and proposal-contract failures remain failures. The fixed build must
pass all four groups normally. No corpus quality, audibility, MCU timing or
physical-board claim follows from these synthetic mechanism checks.

## Measured regression result, 2026-11-26

GCC13.3.0 on Ubuntu24.04/WSL, `-O2 -std=c++11 -ffp-contract=off`, portable C
decoder arithmetic and the production host source/define list. Both four-group
runs passed: the old source had to produce the designated regression exits,
while the fixed source had to pass normally. Source SHA-256 values:

- Old: `c38d113e1c39a5dc0701b5cec87237c9a1611f207f2864e68772eaba684bbfcc`
- Fixed: `cba09bfaab7092612befeab2e2f5af9304787ad7131efa88740bcb58abb1f8a7`

| Contract | Cases | Old coefficient/audio mismatches | Fixed mismatches |
| --- | ---: | ---: | ---: |
| P3 reset/nonzero crops | 294 | 258 / 240 | 0 / 0 |
| P4/P6/P8 controls | 882 | 0 / 0 | 0 / 0 |
| Real-prefix continuation crops | 480 | 108 / 96 | 0 / 0 |

The P3 cases include84 canonical no-op edits and27 later-frame propagation
events. Both sources pass12 deterministic profile/rate proposal contracts,
including18 returned legal, non-no-op, complete-native-verified proposals.
Ignored `independent-pre-fix/receipt.json` and `independent-fixed/receipt.json`
under `build/compact-quality/` retain the exact compiler command, all linked
source/header/table hashes and per-group output. These are correctness checks,
not a measured corpus quality gain.
