# Complete AVR admission of the new V9 bitrate presets

Both presets use the existing universal V9 decoder. A fixed public phrase of
19,200 samples, 2.4 seconds at 8 kHz, was encoded once at each preset and played
completely on ATtiny88 and ATmega328P at 16 MHz. All four complete images passed
the active-interrupt gate: **76,800 exact PWM samples, zero underruns and decoder
errors**, correct EOF, drained FIFO and stopped timers. This is simavr 1.6
evidence for these inputs, not a physical-board or whole-corpus result.

The preset is a complete-file ceiling. The 3 kbit/s P4 result is 887 bytes
against a 900-byte cap. The 8 kbit/s P6 result is 1,480 bytes against a
2,400-byte cap; its actual rate is about 4.93 kbit/s. It is not padded to fill
the budget. In particular, this test does not establish a worst-case timing
bound for every possible 8 kbit/s stream or extra-pulse configuration.

| Target | Preset, kbit/s | Full Flash, B | Program/tables/gain byte, B | Audio, B | Static SRAM, B | Observed stack, B | Minimum FIFO |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ATtiny88 | 3 | 4516 | 3629 | 887 | 418 | 28 | 26 |
| ATtiny88 | 8 | 5110 | 3630 | 1480 | 418 | 28 | 25 |
| ATmega328P | 3 | 3904 | 3017 | 887 | 417 | 24 | 27 |
| ATmega328P | 8 | 4496 | 3016 | 1480 | 417 | 24 | 27 |

All four images also fit their standard bootloader application regions:
6,012 bytes on Tiny88 and 30,720 bytes on ATmega328P. The observed stack margin
is 66 bytes on Tiny and 1,607 bytes on Mega. Full Flash includes the stream and
the neutral Q7 output-gain byte; the program column excludes only audio bytes.
The one-byte program variation is measured linked-image layout.

## Recipe and oracle

The shared production player uses FIFO32/prefill24, LPC interpolation with two
segments, explicit ASM arithmetic and the common reserved-register ASM ISR.
The compiler's real target selects the no-MUL AVR25 path or hardware-MUL AVR5
path. The independently compiled portable C decoder produces the full expected
PWM; every AVR output byte must match. C arithmetic remains selectable, but no
AVR C real-time result is inferred from this ASM admission.

AVR-GCC 7.3.0 uses the existing `-Os -flto -mcall-prologues -mrelax` recipe,
unroll2 and compiler-selected device headers. Tiny uses the catalog's existing
`-fno-gcse -fno-code-hoisting -fno-move-loop-invariants -morder2
-fno-tree-loop-im -fno-tree-ccp` flags. Both targets read their V9 recording
parameters at runtime and use neutral gain 128 stored in ROM. Nano uses D3 / OC2B;
Tiny uses the existing player output. Gain fitting and output normalization are
not used in this comparison.

The corrected observer charges all four hardware IRQ-entry cycles and waits
for RETI to retire. Complete IRQ costs are 35 cycles on Tiny, 35/36 on Mega.
Observed output intervals are 1,997–2,003 cycles on Tiny, 1,999–2,001 on Mega P4,
and 1,998–2,002 on Mega P6, around the 2,000-cycle sample period.
[Anonymous per-image measurements](firmware.json) retain the exact gate values.

After the final encoder-only no-fit fallback was added, both public-phrase
streams were re-encoded. Their complete bytes matched the already admitted
inputs. All four image, timing and PWM receipts and unchanged firmware source
contexts were revalidated rather than treating a different stream as admitted.
Private input hashes, images, source bindings and logs remain in ignored build
storage. No new decoder instructions or assembly optimization are introduced.

## Reproduction

Use the existing public mono PCM16 phrase and the newly built shared encoder:

```text
node web-player/scripts/encode-lpx.mjs web-player/audio/lpx-bread/original.wav build/v9-preset-reproduce/rate-3.lpx --kbps 3
node web-player/scripts/encode-lpx.mjs web-player/audio/lpx-bread/original.wav build/v9-preset-reproduce/rate-8.lpx --kbps 8
```

Create the ignored output directory first. With AVR-GCC, g++, simavr 1.6 and
libelf available, call the existing verifier from the repository root:

```python
from pathlib import Path
import os
import sys
sys.path.insert(0, 'Codecs/LPX/01_ACTIVE_Q0_CODEC/tools')
from verify_attiny88_player import verify

tiny_flags = ('-fno-gcse', '-fno-code-hoisting', '-fno-move-loop-invariants',
              '-morder2', '-fno-tree-loop-im', '-fno-tree-ccp')
for target in ('attiny88', 'atmega328p'):
    for kbps in (3, 8):
        result = verify(Path(f'build/v9-preset-reproduce/rate-{kbps}.lpx'),
            Path(f'build/v9-preset-reproduce/{target}-{kbps}'),
            target=target, nano_pwm=target != 'attiny88',
            wsl='Ubuntu' if os.name == 'nt' else None,
            assembly=True, asm_isr=True, universal=True, queue=32,
            lpc_segments=2, mul16_unroll=2, rom_output_gain=True,
            normalize_output=False, sample_rate=8000,
            extra_flags=tiny_flags if target == 'attiny88' else (),
            flash_limit=8192 if target == 'attiny88' else 30720)
        assert result['accepted'] and result['pwm_exact']
```

Use fresh build subdirectories. The existing common-player description and
target restrictions are in the [AVR player README](../../01_ACTIVE_Q0_CODEC/examples/ATTINY88_V5_PLAYER/README.md).
