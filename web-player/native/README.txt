AVR C/WASM

avr.c is the production firmware-oriented ATtiny13A subset. It preserves the
existing instruction, timer, EEPROM, stack and diagnostic behavior. Unsupported
instructions/peripherals still fail explicitly; this is not a complete MCU.
WASM is the default UI engine; the JS core is also available for playback.
lib/engines.js loads only the selected renderer; WASM is loaded on selection.
Differential CPU tests and benchmarks continue to use lib/avr-reference.js.

Build from the repository root:
  node web-player/scripts/build-wasm.mjs --emsdk C:/path/to/emsdk
Or set EMSDK and omit --emsdk. Emscripten 6.0.12 / Clang 24.0.0git is the
verified compiler. The build invokes clang/wasm-ld with the prepared sysroot
directly, without emcc or writes to the SDK. No npm dependencies.

The committed wasm/avr.wasm is sufficient for playback. wasm/build.json records
the compiler, flags, normalized source/build-script hashes and binary hash.
The module has no host imports, no allocation and one fixed 64-KiB memory per
CPU, including an 8-KiB stack and 4096-frame PCM/raw buffers. C double counters
preserve exact integer clocks beyond 2^32; block-local PC/SREG use integers.
The clock helper is forced inline for the verified Clang build. I/O instructions
already account for their bus cycles; step_cpu calls the remaining clock only
when nonzero, including EEPROM stalls. The exported avr_clock(0) still settles
current events and expired control windows. The 64-cycle block cap and strict
pre-overflow guard are unchanged. Separate add/subtract paths let Clang fold
the ALU operation type; compare-based budgeting retains fmin's single-NaN rule.

avr_layout and avr_field_name expose memory offsets and double state fields.
lib/avr-wasm.js maintains typed views and the existing debugging API, including
instruction hooks and SRAM aliases. An overridden JS step hook disables blocks
for audits. Production rendering enters WASM once per block, not per instruction.
The Worker installs its handler before dynamically loading the selected engine
and serializes init, audio-port and controls while that import completes.

avr_render executes CPU/timer/IRQ, linear resampling, high-pass (35 Hz),
low-pass (UI cutoff, clamped below Nyquist), then gain. Both biquads use Q=0.5
and f64 transposed Direct Form II state. Cutoff and gain changes use 15-ms
exponential smoothing. Raw Float32 values are retained for PWM diagnostics.
Web Audio supplies only the output queue/device, with no duplicate filters.
Coefficient definitions: https://webaudio.github.io/Audio-EQ-Cookbook/audio-eq-cookbook.html
Web Audio Q uses dB; the old graph sets Q to 20*log10(0.5).

Verification:
  node --test web-player/tests/*.test.mjs
  node web-player/scripts/benchmark-wasm.mjs
  node web-player/scripts/benchmark-native.mjs --baseline-ref <commit>
Serve and open /web-player/tests/browser-smoke.html for real Worker and
OfflineAudioContext comparisons. The independent JS DSP uses Direct Form I;
the browser graph has stage rounding differences and is checked within 5e-5
full scale. Reports retain exact binary/source hashes and measurement conditions.

The module links math routines from the Emscripten musl libc and LLVM compiler
runtime. Their complete notices accompany the binary in wasm/LICENSE-musl.txt
and wasm/LICENSE-compiler-rt.txt.
