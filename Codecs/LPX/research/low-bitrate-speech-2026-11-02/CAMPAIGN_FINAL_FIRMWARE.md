# Final same-format campaign firmware admission

All 54 final four-second corpus streams passed complete linked-player simulation on ATmega328P at 16 MHz: 8 kHz sample IRQ, 62.5 kHz Timer2B PWM on Arduino D3. The original pinned decoder and production flags were used. SCALE-RAMP and metadata320 experiments are separate.

| Cap, kbit/s | Jobs | Changed from round0 | Reused identical image | Complete Flash, bytes | Program Flash, bytes | Static SRAM / peak stack, bytes |
| ---: | ---: | ---: | ---: | --- | --- | --- |
| 2 | 27 | 12 | 15 | 5456–5866 | 4879–4880 | 756 / 51–60 |
| 3 | 27 | 11 | 16 | 5988–6074 | 4573–4574 | 756 / 51–60 |

Every image emitted all 32,000 expected PWM samples exactly, drained its queue, stopped once and had zero underruns, decoder errors and observer errors. Queue256/prefill192, explicit AVR5 hardware-MUL assembly and ordinary active output interrupts were used. Portable C remains selectable; these real-time results concern the measured assembly images.

Unchanged streams reused round0 images only after the current production builder rechecked exact input bytes, core/player source, compiler/header/library dependencies, flags, linked images and observer/runtime fingerprints. If a validation fingerprint differed, simulation ran again. Changed data received fresh complete-image admission. The reported Flash includes program, tables, data and exact embedded audio; diagnostic metadata is not linked into the production images.

Observed sample-IRQ intervals span 1997–2003 CPU cycles around the 2,000-cycle period. The smallest observed stack margin was 1231 bytes. Detailed anonymous per-image values are in [the JSON](campaign-final-firmware.json).

This is ISA-simulator evidence with interrupts active, not a physical-board measurement or a browser-host speed guarantee. Private streams, source bindings, images and logs remain in ignored local build storage. No publication or main-branch integration is implied.
