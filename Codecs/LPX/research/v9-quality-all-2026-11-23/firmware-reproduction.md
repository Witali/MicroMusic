# Final-stream firmware validation

`firmware.py` keeps preparation, compilation and simulation separate. Each run
needs a fresh private output directory and the explicit final decoder/player
commit. The script freezes tracked decoder, profile, player, builder, observer
and vendor-header sources from that commit. Firmware and portable C references
compile from the same immutable source. Later worktree changes do not change
the measured program.

Run these stages only when the validation schedule has released a worker:

```text
python firmware.py prepare --output build/final-avr --core-sha FINAL_COMMIT --case public-k8 build/final-input/baseline-k8.lpx build/final-input/candidate-k8.lpx
python firmware.py build --output build/final-avr
python firmware.py run --output build/final-avr
```

`prepare` performs no compilation or audio decoding. `build` compiles images,
portable C references and calibrated observers without executing a decoder or
simulator. `run` executes one image at a time with simavr 1.6 and active IRQs.
An additional `--case` can supply the final strict 3 kbit/s pair. If adjacent
`.u8` host outputs exist, preparation freezes them too and every final portable
C reference must match them before AVR admission can proceed.
Use `--candidate LABEL INPUT` instead of a paired `--case` when only final
candidate admission is scheduled; two candidates produce six default images.

Default configurations are Tiny88 ASM, Mega328P ASM and Mega328P C arithmetic
with C ISR. ASM is explicitly enabled only through the existing target-aware
backend. The recipes use the compiler's device headers, 16 MHz, 8 kHz, universal
runtime headers, FIFO32/prefill24, two LPC segments, multiplication unroll2 and
neutral ROM player gain128. No file-gain feature is forced on or off: the pinned
final decoder determines its support. Primary inputs must contain no gain or
Long metadata. Input-level planning belongs to the encoder.

Pass `--prior-tiny-c` to retain the earlier private Tiny C failure receipt as
explicitly historical. It is never relabeled with the current source or stream
revision. `--include-tiny-c` requests a new C fallback measurement if a source
change warrants one. Availability of C arithmetic does not establish real-time
support. A failed timing or stack case remains a failure in the output.

Admission requires all samples to match the separately compiled C decoder,
exact sample/tick/timer-event counts, zero underruns and decoder errors, correct
EOF, drained FIFO, stopped sample timers, complete four-cycle IRQ entry and RETI,
positive stack margin and the existing full-image/RAM limits. Flash includes
the exact embedded stream. Bootloader-region fit is reported separately.

All source bindings, input hashes, images, logs and receipts stay below ignored
`build/`. Only anonymous numeric fields appear on stdout. Prior V2 measurements
against the gain-enabled `9d15e9f9` core remain historical. New measurements
must name the final stream and core actually tested. Simulation of a fixed
8 kHz phrase establishes no higher-rate, arbitrary-stream or physical-board
support claim.
