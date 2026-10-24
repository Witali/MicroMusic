# ATtiny13A acquisition transport

These tools retain raw observations and provenance. A decoded capture is
unreviewed evidence; it does not automatically validate a peripheral model,
select an ADC interpretation or close a silicon acceptance item. Synthetic
checks must remain labeled synthetic.

## Wire-v2

`probe-wire.inc` is project-owned assembly. Include the existing official
`../attiny13a-registers.generated.inc` first, then define
`PROBE_WIRE_CLOCK_BIT` and `PROBE_WIRE_DATA_BIT` as Port B bit positions. Configure
their outputs before calling `probe_emit_frame`. Hold trace clock low before
the first frame. A documented weak external pulldown, for example100kΩ, on the
trace-clock line establishes that idle level while the chip is in RESET/HiZ.
Record its value and probe loading. Keep programmer drives released during
acquisition; no virtual programming transport is implemented.

The frame is14 bytes, MSB first, sampled at trace-clock rising edges:

| Bytes | Meaning |
|---|---|
|0–1|Sync a5 5a|
|2|Wire version2, distinct from the old Timer0-specific wire-v1|
|3–4|Probe ID from r4, build-profile ID from r5|
|5–6|Sequence low/high from r2/r3|
|7–12|Six raw data bytes from r6..r11|
|13|XOR of all eleven payload bytes|

The sender clobbers r12/r17/r18/SREG and preserves other registers. Snapshot
measurement flags before calling it. Maximum nested return storage is four
SRAM bytes. Data meanings, overloaded boot fields and sequence policy belong
to the probe descriptor. Frame start/end timestamps locate serialized bits,
not internal peripheral events.

## Decoder and raw capture

```text
python web-player/native/peripherals/hardware-probe-test.py
python web-player/native/peripherals/hardware-probe-decode.py capture.csv --config probe.json --profile PROFILE --capture-kind synthetic -o decoded.json
```

Use `--capture-kind hardware --measurements conditions.json` for actual captured
data. The descriptor selects mandatory waveform columns, probe/profile IDs,
record count when fixed and sequence policy. CSV starts before boot with trace
clock low. Timestamps are finite, monotonic seconds; clock/data are digital0/1.
Keep the complete original analog/digital acquisition and exported CSV. JSON
retains their reference/hash rather than duplicating the waveform.

Hardware conditions must identify the measured device/configuration and stated
uncertainty. This is a structural example; replace every fixture value with
actual measurements before using it for hardware evidence:

```json
{
  "chipMarking": "actual package marking",
  "chipRevision": null,
  "vccVolts": 5.0,
  "temperatureC": 25.0,
  "clockHz": 1000000.0,
  "fuses": {"low": "0x70", "high": "0xff", "lock": "0xff"},
  "instrument": {"name": "actual model", "sampleRateHz": 100000000,
                 "thresholdVolts": 2.5, "notes": "record bandwidth, channel skew and loading"},
  "timingToleranceSeconds": 0.00000001
}
```

An unknown chip revision is explicitly null. Add actual analog stimulus/settling,
probe loading, fuse readback and package details. Minimum keys alone are not a
calibration or a complete uncertainty analysis. Keep ELF/programmed-image hashes
with the lab record. Decoder identities include the actual source, descriptor,
shared sender, register definitions and capture. `--source FILE` selects the
actual source when an alternate build was used.

Strict decoding rejects checksum, version, identity, sequence and framing errors.
For an intentional RESET reassertion inside serialization, the reset-to-zero
descriptor accepts `--allow-reset-fragments`. It searches for complete matching
frames while recording **every** unframed bit range, its count and timestamps;
`transportQuality` becomes `unframed-bits-retained`. Partial records are never
invented. Inspect the raw acquisition: resynchronization does not establish why
a fragment occurred or prove that no reset/event was missed. Other probe types
cannot enable this recovery mode. Repeated boot sequence0 is valid only for
reset-to-zero descriptors.

The synthetic tests exercise arbitrary observed bytes, wire-v1 rejection,
corruption, identity/sequence errors, timing/digital input errors, interrupted
resets, required conditions and alternate-source provenance.

## Manufacturer definitions

Register offsets, bit positions and memory constants come from pinned official
Microchip ATtiny_DFP3.4.278 originals, through the generated assembly view.
Originals remain unmodified, with their licenses and hashes.

Pin functions also require the
[ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
Figure1-1/Table10-3. This pack's ATDF omits CLKI/RESET pad signals and names ADC
signals PA0..PA3 despite declaring PORTB. Do not infer physical ADC pads from
those aliases: the data sheet assigns ADC1 to PB2, CLKI to PB3 and RESET to PB5.
Descriptors retain those explicit adaptations separately from vendor files.
TC0/T and OC0A/B signals in the ATDF do name the PB pads.

See [manufacturer provenance](../../vendor/microchip/ATtiny_DFP/3.4.278/README.md).
