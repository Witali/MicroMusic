# CPU phase acquisition firmware — pending hardware

This is executable **acquisition tooling**, not a silicon timing result.
`cpu-phase-probe.S` has 22 independently built profiles; the descriptor retains
`expectedSiliconTrace:null`. The verifier runs those real AVR images through
the generated CPU/native device to check the acquisition program and the current
digital conventions. Those synthetic captures must never become hardware evidence.

Manufacturer references are Microchip's [AVR Instruction Set Manual
DS40002198A](https://ww1.microchip.com/downloads/en/DeviceDoc/AVR-Instruction-Set-Manual-DS40002198A.pdf)
(PUSH/POP, calls/returns, LD/ST, LPM and skip instructions), and
[ATtiny13A DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
sections 4.5–4.7, 5.2.1, 8.1–8.2 and 10.2.4. They specify stack ordering,
instruction totals, SRAM timing concepts, reset behavior and synchronized PIN
reads. They do not publish all internal byte-access phases. The exact C2/C3/C4
and read-latch choices under test are explicitly documented in
[`AVR_TO_WASM.md`](../AVR_TO_WASM.md#instruction-effect-timing).

The source directly includes the pinned, unmodified Microchip `iotn13a.h` with
numeric `_SFR_IO8/_SFR_IO16` adaptation. The generated manufacturer view supplies
common CPU symbols such as SPL, absent from that device C header. Register,
bit and memory addresses are not a handwritten alternate map. See the pinned
[DFP provenance](../../vendor/microchip/ATtiny_DFP/3.4.278/README.md).

## Wiring and safe acquisition order

| Pad | Role |
| --- | --- |
| PB0 | Driven target marker; optional documented 47 kΩ pulldown for RESET/HiZ observation |
| PB1 | External ARM input; real INT0 source in profile 7 |
| PB2 | Wire-v2 trace clock; weak documented pulldown establishes RESET idle |
| PB3 | Continuous external CLKI, 4000 Hz, 125 µs high and low |
| PB4 | Wire-v2 trace data |
| PB5 | Physical RESET input, analog waveform retained |

DDRB is 0x15: marker and two wire outputs only. Low/high/lock fuses are
0x70/0xff/0xff: CKSEL00, CLKPR initially /1, SUT00, ordinary RESET role and DWEN
unprogrammed. Firmware does not write CLKPR or OSCCAL. The deliberately slow
4 kHz source is a fully static core acquisition fixture. It has no connection
to a debugWIRE frequency requirement; this firmware does not use debugWIRE.
Use stable measured VCC and record actual source levels, slew and loading.

Start acquisition with ARM low and RESET released after a known reset control.
Wait for both boot frames and let their sender return. Supply a **fresh low then
high ARM** for each boot; keep it high through the target. For another attempt,
assert RESET, drop ARM while RESET is held, then release RESET with ARM low.
Firmware never automatically rearms a completed target. Shared programmer drives
must be released before acquisition; virtual ISP/HVSP remains excluded.

Retain analog RESET, VCC and marker waveforms, plus digital CLKI, ARM, marker,
wire clock and data. CSV names are
`time_s,clock,data,clki,vcc,marker,arm,reset`; `vcc`/`reset` are measured volts.
Keep original analog channels and channel skew, threshold, bandwidth, sample
rate, resistor/capacitance, device/revision, temperature and fuse readback records.
Thresholded CSV alone does not establish internal reset recognition.

## Snapshot and target placement

The first handler instruction saves MCUSR. Six direct STS instructions then save
old r0/r20/Xlo/Xhi/Zlo/Zhi **before changing any of them**. Boot frames are sent
before test sentinels or the magic tag are initialized. Stack is restored to
RAMEND before the sender is called.

All offsets derive from official RAMSTART:

| Region | Offset | Purpose |
| --- | --- | --- |
| TEST0..3 | +16..19 | Four observed target/stack bytes |
| Magic | +20 | 0xa5, written last after ARM/setup |
| Snapshots | +32..43 | Six old and six completed GPR bytes |
| Encoder stack | RAMEND downward, at most four bytes | Disjoint from test and snapshots |

After fresh ARM the sentinels become 11/22/33/44, r0=55, r20=e7 and X=TEST1.
Z references actual Flash data a9/36, except ICALL's actual callee word address.
LPM r20,Z starts on odd byte36; the bare and Z+ variants start on even bytea9.
RET/RETI preloads a legitimate return frame in TEST0/1. PUSH/calls/IRQ use a
test stack over TEST0/1; completion restores the real encoder stack before any
RCALL. The magic tag identifies an initialized attempt; its retention is still
an observation, not a substitute for physical controls.

Every build places the prelude at word 253, marker OUT at 254 and target at 255.
Prelude is NOP, or SEI for IRQ. The verifier checks ELF symbols using `avr-nm`;
callee, data and return addresses come from those labels. RCALL/ICALL therefore
exercise a return address across the low-byte boundary without a guessed PC.
The call callee lowers the marker **before RET**, bracketing call3+OUT1.

Profile 7 configures rising INT0 on ARM while I is clear. SEI at word253 executes
the following marker OUT before accepting the pending interrupt. Entry uses
the real stack and vector RJMP; the handler lowers the marker and executes
RETI, returning to NOP at word255. No fake CALL or manual IRQ acknowledgment
replaces that path. Marker bracketing includes vector instructions explicitly.

| Profiles | Target |
| --- | --- |
| 0 | NOP; mandatory physical GPR/SRAM retention control |
| 1–2 | PUSH/POP r20 |
| 3–4 | RCALL/ICALL |
| 5–6 | RET/RETI with preloaded frame |
| 7 | Pending INT0, genuine IRQ entry/RETI, then NOP |
| 8–13 | LD/ST r20 with X, X+ and -X |
| 14–15 | Two-word LDS/STS TEST1 |
| 16–18 | LPM r0, LPM r20,Z and LPM r20,Z+ |
| 19 | Immediate IN r20,PINB after marker OUT |
| 20–21 | SBIS/SBIC ARM; following two-word STS TEST2 is skipped/executed |

## Raw record policy

Shared [`probe-wire.inc`](probe-wire.inc) emits wire-v2, probe ID 4 and the
selected profile ID. Sequence is **restartable-pairs**:

| Sequence | Six data bytes |
| --- | --- |
| 0 | Saved MCUSR, old magic, old TEST0/1/2/3 |
| 1 | Old r0, r20, Xlo, Xhi, Zlo, Zhi |
| 2 | Zero, completed magic, completed TEST0/1/2/3 |
| 3 | Completed r0, r20, Xlo, Xhi, Zlo, Zhi |

0/1 is one boot pair; 2/3 is its optional completion pair. Each reset restarts
at 0. Thus 0,1,2,3 and 0,1,0,1 are valid. Strict decoding rejects missing
partners, duplicated/interchanged records and trailing incomplete pairs.
`--allow-reset-fragments` explicitly retains unframed bit ranges and
`sequenceGaps`, including an interrupted pair with otherwise complete frames.
Transport quality changes accordingly; missing observations are never invented.
Frame start/end locate serialization, not the target memory event.

GPR reset retention is **not assumed for a chip**. Run profile 0 on the actual
device and conditions first; repeat as a control for every sweep. If raw retained
GPRs are not reliable, mark the GPR-based result unqualified rather than deriving
an instruction phase. Old SP/SREG are reset I/O state and are not captured here.
Unchanged SRAM in RET/RETI cannot expose its individual read-latch phases; these
profiles check frame/control-flow setup and provide reset observations only.

## Software verifier and physical sweeps

```text
node web-player/scripts/verify-cpu-phase-probe.mjs
node web-player/scripts/verify-cpu-phase-probe.mjs --profile rcall --cuts none
python web-player/native/peripherals/hardware-probe-test.py
```

The script locates prepared AVR GCC7.3.0 and Python3.13.3, or accepts `--avr-bin`
and `--python`. `--profile` selects one descriptor ID; `--cuts none` keeps only
uncut execution. `--out` defaults to ignored `build/cpu-phase-probe-verification/`.
It compiles actual source, verifies image size/symbols, runs generated CPU/native
WASM with 4 kHz periodic CLKI, drains pins in bounded 128-source-half slices,
writes synthetic CSV and invokes the shared decoder. Summary records exact
source/config/wire/header/script/runtime/library/image identities and parameters.
Raw data remain fully retained, even when an assertion masks an unqualified bit.

An uncut preview locates the physical marker in the **software fixture**. Every
reset cut is then queued in a fresh device **before execution**: no JS callback
races the marker. At time0 the driver mask is ARM|RESET=34, levels32; ARM goes
high at 2 s (levels34). A cut drives levels2, lowers ARM during RESET, then
releases with levels32. Reset is prequalified digital input in these controls.
The verifier asserts current model memory/GPR commitments and RESET tie priority,
not analog reset acceptance. The source and image are identical for preview/cuts.

IN has an independent GPIO oracle: immediate OUT→IN sees old PB0 low, stable ARM
high, trace clock low, old PB4 from the pre-marker physical pin trace and PB5
digital read disabled by its RESET role. Only the CLKI self-read bit is masked;
the raw byte remains in both captures. No observed IN destination becomes its
own expected value. Other target results and stack bytes derive from sentinels,
ELF labels and the explicitly selected digital phase convention.

For physical acquisition, sweep reset timing around the marker with measured
tolerance and repeat controls; do not transfer the verifier's ±1 ps cuts into a
silicon assertion. Marker pad propagation, reset receiver recognition, stimulus
slew, loading and channel skew shift the relation to internal clock phases.
GPR snapshots after reset are conditional evidence, not a view of hidden latches.
This tooling neither selects new default CPU phases nor closes their outstanding
hardware validation. Preserve raw captures and provenance for that later review.

The software checkpoint exercises all 22 compiled profiles and 114 queued reset
cuts (136 runs), with image sizes 710/712/714 bytes and zero data/BSS. It also
retains 18 shared protocol checks and five legacy Timer0 decoder checks. These
are functional tooling/model checks; no silicon capture is supplied or inferred.
