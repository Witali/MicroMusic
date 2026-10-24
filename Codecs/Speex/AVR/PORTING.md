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
| Generic, bounded and aligned-p1 Q14 products | `q14.S` | exact word extraction in `nb3_c_math.h`, selected by `avr_fixed.h` |
| LSP polynomial stages | `compact_lsp.c.inc` calling Q14 ASM | same recurrence using C Q14 |
| Historical pitch write/add | `pitch_add.S` | C block loop in `pitch24.h` |
| Innovation, scaling and saturation | `innovation.S` | C branch in `innovation.h` and bounded helpers in `nb3_c_math.h` |
| Known-zero adaptive gain | separate `speex_avr_zero_innovation10` entry | four byte products/carries in `speex_nb3_zero_shape_c` |
| Zero-tail vectors (0..10) | `speex_avr_zero_innovation_n`, shared fixed-ten body | explicitly selectable helper in `zero_innovation.h`; controller retains the measured faster prior C loop |
| Fused long-pitch/innovation | second entry in `innovation.S`, shared scaling/clamps | `long_pitch.h`, inlined into the C forty-sample caller |
| Variable-count fused vectors (0..10) | separate entry in `innovation.S`, same scaling/clamps | `long_pitch.h` with runtime count |
| One-sample fused vectors | scalar entry in `innovation.S`, same transform with fewer saved registers | same `long_pitch.h` helper with count=1 |
| Short-pitch range selection and boundary sums | `short_pitch.h` calling variable ASM vectors | `short_pitch.h`, scalar boundaries and inlined C vectors |
| Whole-block LPC synthesis | `lpc_dot.S` | C dot product and coefficient-age loop in `iir_direct.c.inc` |
| Four consecutive innovation indices | bounded C group in `nb3_indices.h` | same portable C helper; partial/other-offset states use four generic reads |

The AVR IIR cursor compares a low address byte only because ten word positions
span exactly 20 bytes; every state-base low byte and page crossing is tested.
Changing that span requires a new wrap proof. The portable C IIR retains its
ordinary indexed ring cursor and coefficient-age loop.

The C build does not link any `.S` file. The historical, unused
`lpc_update.S` corresponds to upstream transposed C synthesis and is not a
library dependency. The optional player load-test markers are instrumentation,
not decoder kernels.

Preserve upstream Q14's two-term decomposition and its signed16 high-word
cast. Replacing it with a seemingly equivalent wide multiply/shift changes
results outside the bounded polynomial range. Keep rounding, modulo-32 sums
and saturation identical in every backend.

The zero-adaptive transform alone has a stronger bound: signed8 shape and
0..121,000,000 scale give s16 output without saturation. Its mathematical
shape*scale product can require 35 signed bits; do not implement the folded
formula with a wrapping signed32 multiply. The C byte-product carry cascade
and ASM partial products avoid that intermediate. Other submodes or nonzero
adaptive sums need their own bounds and original clamps.

AVR commands, from the repository worktree root:

```sh
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc --backend c
node Codecs/Speex/AVR/tests/verify_avr.mjs --backend c --verify-reset
python Codecs/Speex/AVR/tools/build.py --avr-gcc avr-gcc --backend asm
```

The verifier checks the binary hash against its backend metadata and rejects
linked ASM kernels in a C build. C is a correctness/portability fallback;
real-time support depends on the target and must be measured. On ATmega328P
both C and explicitly enabled ASM pass all 31 complete PWM streams with
interrupts. The tested additional CPU reserve is 10% for C and 40% for ASM;
these are measured corpus/ISA results, not physical-board guarantees. The
C corpus maximum is 253,039 cycles (253,604 with pitch coverage).
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
  `abort` dependency. The embedded path uses the same 60-byte arena. The live
  quantized LSP array takes the first 20 bytes. Excitation needs no other
  scratch; the zero-gain path directly rounds its bounded shape/scale product.
  After all excitation, separate LPC and interpolated-LSP arrays occupy
  offsets 20 and 40. Provide
  normal C runtime `memcpy`, `memmove`, `memset`; a hosted OS is unnecessary.
- GCC-specific optimization attributes are isolated in `speex_platform.h` and
  disappear for other compilers. Target-specific intrinsic/ASM optimizations
  must retain a selectable C implementation and exact arithmetic behavior.

Validate upstream PCM, reset/invalid calls, stack/SRAM and the actual output
peripheral with interrupts/DMA active on each new CPU. AVR measurements do not
establish ARM, RISC-V or another MCU's timing or board support. Native WB/UWB
profiles remain separate experiments and are not enabled by choosing C.

The AVR IIR uses separate ten-sample coefficient-age and thirty-sample steady
loops, caching two coefficient words in registers after the age transition.
This changes neither its 60-byte state nor the portable C recurrence.
The newer grouped index reader is C in both backends. Its two overlapping
16-bit windows read three bytes only after checking availability; fallback
preserves the generic reader's partial/sticky-overflow behavior. It does not
assume native byte order or unaligned word loads. All 14,278 AVR frames per
backend and four normal/loaded PWM matrices are exact. Architecture/enable
selection passes twelve real-compiler cases; fresh manifest/CMake C archives
each match 9,100 host frames. These checks do not measure another MCU's
performance. See `reports/nb3-indices-admission-audit.json` and
`reports/portable-nb3-indices-library.json`.

Reproducible portability checks:

```sh
python Codecs/Speex/AVR/tests/verify_backend_selection.py --cc clang --avr-gcc avr-gcc
python Codecs/Speex/AVR/tests/verify_portable.py --cc clang --ar llvm-ar --cmake cmake --ninja ninja
```

The second test exports a fresh package, builds both manifest and CMake static
archives, and links a consumer with public includes only. It compares complete
prepared fixture/human-speech streams with upstream. It requires the reference
host decoder built first; human-speech coverage is included when those streams
are prepared. `reports/portable-segment-library.json` records the current
31-stream run through both build paths.
