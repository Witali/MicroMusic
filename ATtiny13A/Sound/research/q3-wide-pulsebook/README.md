# Fractional-state precision diagnostic: reproducible negative result

This is a PC-only diagnostic on four frozen Vinni models, not a new MCU core.
It preserves the source timing/pulsebook/coefficients while testing fractional
internal states. Existing parameters are not jointly refitted for the new
arithmetic. No AVR Flash, SRAM, cycle count or hardware feasibility is claimed.

The original incomplete44-row scratch screen lacked source/configuration/guard
provenance. A complete new48-case capture is retained here, with all rejected
combinations. The old build-only scratch file remains untouched.

## Complete grid and exact policies

Four source models, in report order:

1. `research/hq4-q3/public-vinni/model.json`;
2. `research/q3-rounded-eeprom/qualified/model.json`;
3. `build/q3-pulsebook/vinni/best_spectrum/model.json`;
4. `build/q3-pulsebook/vinni/best_stoi/model.json`.

The latter two have identical retained counterparts in
`research/q3-pulsebook/vinni/`. The runner explicitly resolves those counterparts
if the temporary files are missing; requested/resolved paths and actual hashes
remain recorded. Complete input parameter snapshots are also in `report.json`:
packed HQ4 stream base64, signed64-entry pulsebook, schema, tilt, sample count,
source rounding and source/model/table hashes.

Every input tests2/4 fractional bits, floor/nearest internal products and encoded
gain scales.65/1/1.35, producing4x2x2x3=48 cases. Gain is exactly
`min(15,rint(old_gain*scale))` with NumPy ties-to-even; source mode bits are
preserved. Pulsebook is the model's table or exact legacy tables. The -15/16
mapping is used only when schema is `hq4-q3-pulsebook-pole-v1`.

Wide states are audited against signed16 product/lattice/T1 limits. PWM rounding
is always nearest, independently of the internal-product rounding switch.
PWM overflow is counted before modulo conversion; any guard event rejects the
case, and wrapped audio is not given valid STOI/spectral scores. There is no
limiter, reference normalization, DC removal, cropping or resampling.

## Measured results

All48 combinations are present:44 complete,4 rejected. The rejected cases are
the spectrum-oriented source at gain1.35, for both fractional precisions and
both internal rounding choices. They produce6/2/4/4 signed8 PWM overflow events;
their signed16 product/lattice/T1 counts are zero. These deliberately amplified
diagnostic variants are separate from the current-gallery clipping audit.

| Endpoint | STOI | Spectrum loss | Corresponding byte-model STOI / spectrum |
|---|---:|---:|---:|
| Highest diagnostic STOI | .822957 | .506447 | .840448 / .504474 |
| Lowest diagnostic spectrum error | .802322 | .467180 | .802536 / .468277 |

The valid endpoint measurements reproduce the earlier scratch values exactly,
but the new capture now makes source data and exclusions auditable. The highest
STOI decreases relative to its byte-model control. The small spectral gain at
the other endpoint comes with slightly lower STOI. No case meets the requested
joint STOI>=.90 / spectrum<=.344975554 target.

This supports retaining fractional precision as a negative fixed-parameter
diagnostic, not adopting it as a demonstrated improvement. It does not prove
that wider arithmetic could never improve quality after a new joint fit.

## Reproduce and check

```powershell
python tools/probe-q3-wide-pulsebook.py `
  --reference web-player/audio/originals/vinni.wav `
  --output build/q3-wide-pulsebook-repro/report.json
python tools/test-q3-wide-pulsebook.py
```

Reference SHA-256 is
`749d710e639070750f7b91016672b8030f07fa0494a2275db2eb073b33a99e03`.
The report retains reference/model/table/parameter/source/PCM hashes, complete
guard counts and maxima, raw output level statistics, all policies, input byte
controls and runtime versions. No audio/raw/compiled files are committed.

Five focused tests cover zero-fraction compatibility with clean floor/nearest
byte controls, the separate -15/16 mapping, independent fractional T1/PWM
recurrence, visible unsafe signed16/PWM cases, and the full grid's exact gain
rounding/clamp/mode behavior. The only cleanup to the initial diagnostic module
removes its unused `product=-ex` assignment; numerical behavior is unchanged.
