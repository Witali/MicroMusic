# Using NB3 on another architecture

The fixed-point C decoder and the AVR assembly backend implement the same
restricted Speex NB3 profile: mono 8 kHz, 20-byte packets, 160 signed16 samples.
The library has no timer, PWM, GPIO, operating-system or heap dependency.
It keeps one static, non-reentrant decoder; reset it before each stream.
The AVR PWM demo in `src/player.c` is a separate hardware integration.

## Backend selection and C fallbacks

`SPEEX_NB3_ARCH` identifies the architecture. It defaults from the compiler's
native architecture macros (`__AVR__`, `__arm__`, `__riscv`, etc.), or can be
provided by a platform/manufacturer header. Values are `SPEEX_NB3_ARCH_AVR`,
`SPEEX_NB3_ARCH_ARM`, `SPEEX_NB3_ARCH_RISCV` and `SPEEX_NB3_ARCH_GENERIC`.

`SPEEX_NB3_ENABLE_ASM=1` explicitly permits handwritten assembly. Its default
is **0 on every CPU, including AVR**. AVR ASM is selected only when the
architecture is AVR, ASM is enabled, and the compiler provides the supported
classic AVR ABI with hardware MUL. If any condition is absent, or no optimized
backend exists for the chosen architecture, use C. `SPEEX_NB3_USE_AVR_ASM` is
the internal derived result, not a user setting.

For example, a platform header may include the manufacturer's device header
and define `SPEEX_NB3_ARCH` plus `SPEEX_NB3_ENABLE_ASM` together. Pass its path
with `SPEEX_NB3_PLATFORM_HEADER="my_port.h"`. Keep real compiler architecture
macros: never undefine `__AVR__` to obtain C. AVR still requires its Flash reads
when using C arithmetic. Those reads follow the actual memory model,
independently of the requested arithmetic backend.

```c
/* In an AVR platform configuration header, after the manufacturer's header: */
#define SPEEX_NB3_ARCH SPEEX_NB3_ARCH_AVR
#define SPEEX_NB3_ENABLE_ASM 1
```

Omit the second define, or set it to 0, to select C on the same AVR. ARM,
RISC-V and unknown architecture values use C even with ASM enabled, since no
matching optimized kernel is provided yet.

| Optimized operation | AVR implementation | C fallback |
| --- | --- | --- |
| Signed 16x16 multiply | `avr_multiply.h` | exact-width C multiply in that header / upstream `fixed_generic.h` |
| Signed shifts and rounded products | `avr_shift.h`, `avr_fixed.h` | C shifts in `avr_shift.h` / upstream fixed-point macros |
| Generic and bounded Q14 product | `q14.S` | upstream `MULT16_32_Q14` in `fixed_generic.h` |
| LSP polynomial stages | `compact_lsp.c.inc` calling Q14 ASM | same recurrence using C Q14 |
| Pitch write/add | `pitch_add.S` | C block loop in `pitch24.h` |
| Innovation, scaling and saturation | `innovation.S` | C branch in `innovation.h` |
| Whole-block LPC synthesis | `lpc_dot.S` | C dot product and coefficient-age loop in `iir_direct.c.inc` |

The C build does not link any `.S` file. The historical, unused
`lpc_update.S` corresponds to upstream transposed C synthesis and is not a
library dependency. The optional player load-test markers are instrumentation,
not decoder kernels.

Preserve upstream Q14's two-term decomposition and its signed16 high-word
cast. Replacing it with a seemingly equivalent wide multiply/shift changes
results outside the bounded polynomial range. Keep rounding, modulo-32 sums
and saturation identical in every backend.

AVR commands, from the repository worktree root:

```sh
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc --backend c
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend c --verify-reset
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc --backend asm
```

The verifier checks the binary hash against its backend metadata and rejects
linked ASM kernels in a C build. C is a correctness/portability fallback;
real-time support depends on the target and must be measured. On ATmega328P
the C decoder core fits the measured 20-ms frame budget, but the complete
player still underruns on long audio with timer/ISR and output costs.
The build tool defaults to C; `--backend asm` explicitly adds the enable define.

## Export and integrate

Create a new export directory (an existing directory is never overwritten):

```sh
python Codecs/Speex/AVR/tools/build.py --export-c Codecs/Speex/AVR/build/portable-nb3
cmake -S Codecs/Speex/AVR/build/portable-nb3 -B Codecs/Speex/AVR/build/portable-build -DCMAKE_BUILD_TYPE=Release -DCMAKE_TOOLCHAIN_FILE=/path/to/your-toolchain.cmake
cmake --build Codecs/Speex/AVR/build/portable-build
```

The exported package contains generated C sources, required headers, the Xiph
BSD license, an explicit `sources.json` manifest and `SHA256.json`. It contains
no test main, AVR player or `.S` source. Include it with CMake `add_subdirectory`
and link target `speex_nb3`, or use the source/define/include lists in
`sources.json` in an existing build. The supplied CMake target uses the C
backend, disables scratch instrumentation and exports its public include path.
The `SPEEX_AVR_*` profile defines are retained implementation names; they do not
select an AVR instruction set.

```c
#include "speex_nb3.h"
/* Use application-owned buffers; do not allocate them in an audio ISR. */
static int16_t pcm[SPEEX_NB3_FRAME_SAMPLES];
/* At stream start: speex_nb3_init(); */
int decode_packet(const uint8_t packet[SPEEX_NB3_PACKET_BYTES])
{
    return speex_nb3_decode(packet, SPEEX_NB3_PACKET_BYTES, pcm);
}
```

The neutral API names are source aliases for the retained `speex_avr_*` ABI.
The older `speex_avr.h` remains compatible. Packet bytes are MSB-first; PCM
uses the CPU's native `int16_t` representation. Convert its byte order only at
an external serialization boundary. Feed PCM to the target's own DMA/DAC/I2S
or PWM code; the decoder does not know which output peripheral is used.

## Platform contract

- C11, 8-bit bytes, exact 16/32-bit two's-complement integers, arithmetic signed
  right shifts, wrapping signed overflow and truncating integer narrowing.
  GCC/Clang require `-fwrapv -fno-strict-aliasing`; keep these for all library
  translation units. This matches upstream fixed-point arithmetic. Other
  compiler families need equivalent settings and correctness verification.
- Tables default to ordinary read-only `const` storage outside AVR. On Harvard
  AVR they retain PROGMEM plus explicit signed byte/word/dword reads. A custom
  memory layout can define `SPEEX_NB3_PLATFORM_HEADER="my_port.h"`, and that
  header must provide `SPEEX_NB3_TABLE` and all of `SPEEX_NB3_READ_I8(p)`,
  `SPEEX_NB3_READ_I16(p)`, `SPEEX_NB3_READ_I32(p)` together. Keep their signed
  types and return the stored integer value, independent of byte order.
- Scratch is explicitly aligned to four bytes using C11 `_Alignas(4)`;
  pointer alignment uses `uintptr_t`, not `long`. No CPU-register layout or
  CPU endianness is assumed by the C arithmetic kernels. Internal packed
  signed24 pitch storage uses three explicit low-to-high bytes; `packed24.h`
  assembles them by value, independent of native byte order or alignment.
- `SPEEX_NB3_CHECK_SCRATCH=0` removes the host-only bounds checker and its
  `abort` dependency. The embedded path uses the same 180-byte arena. Provide
  normal C runtime `memcpy`, `memmove`, `memset`; a hosted OS is unnecessary.
- GCC-specific optimization attributes are isolated in `speex_platform.h` and
  disappear for other compilers. Target-specific intrinsic/ASM optimizations
  must retain a selectable C implementation and exact arithmetic behavior.

Validate upstream PCM, reset/invalid calls, stack/SRAM and the actual output
peripheral with interrupts/DMA active on each new CPU. AVR measurements do not
establish ARM, RISC-V or another MCU's timing or board support. Native WB/UWB
profiles remain separate experiments and are not enabled by choosing C.

Reproducible portability checks:

```sh
python Codecs/Speex/AVR/tests/verify_backend_selection.py --cc clang --avr-gcc avr-gcc
python Codecs/Speex/AVR/tests/verify_portable.py --cc clang --ar llvm-ar --cmake cmake --ninja ninja
```

The second test exports a fresh package, builds both manifest and CMake static
archives, and links a consumer with public includes only. It compares complete
prepared fixture/human-speech streams with upstream. It requires the reference
host decoder built first; human-speech coverage is included when those streams
are prepared. `reports/portable-loop-hoist-library.json` records the current 31-stream run.
