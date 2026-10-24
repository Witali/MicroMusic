# ATtiny13A debugWIRE admission correction, 2026-10-24

The native board previously accepted programmed DWEN unless the optional analog
RESET receiver was enabled. At parent `df914f1`, constructing the ordinary
runtime with high fuse `0xf7`, then injecting low PB5 at time0, returned
`resetHeld:true, resetCount:1`. This applied ordinary RESET to the debugWIRE pad.

## Manufacturer evidence and remaining work

[DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf#page=102),
sections15.3–15.5, describes the open-drain PB5 gateway and pull-up for programmed
DWEN with unprogrammed lock bits, preserves CKSEL clock selection, excludes
external RESET and notes additional running clock circuitry in sleep. The
retained definitions do not supply the startup/debug control contract or a wire
protocol. Section17.1 and Table17-2 also conflict on locked-device debug access;
the implementation does not derive a complete fuse/lock truth table from them.

Programmed DWEN is now rejected for every clock/reset profile, RSTDISBL setting
and lock value. This is an explicit unsupported-mode boundary. It does not
implement the documented debugWIRE pin mux, sleep clocks, debugger startup or
transport; those remain open in the full-device plan. The diagnostic host
`debugEnabled` option remains separate and does not establish fuse-enabled OCD
state on a physical chip. No programming interface is added.

## Change and validation

- Native `device_init` returns config fault1/detail14 before touching caller
  data, Flash or EEPROM. Reinitializing with unprogrammed DWEN still succeeds.
- Public runtime construction rejects programmed DWEN before instantiation,
  covering original v1/v3 binaries that lack the native guard.
- Package creation and loading reject it in configuration validation; loading
  valid historical package schemas remains supported.
- Regressions vary high fuses `f7/f6/e7/e6`, lock bytes `ff/fe/fd/fc` and
  compatible, physical OSCCAL, external CLKI and analog RESET modes. They also
  check the distributed native module directly, actual original v1/v3 runtime
  binaries, package schemas1–5 and retained ordinary RESET/RSTDISBL behavior.

Before the fix, the new focused DWEN checks failed9/11, including missing native,
runtime and package rejection; the existing analog-only/public boundary and
ordinary RESET control passed. The first post-fix focused run passed38/38;
the final14 DWEN tests also passed, including the distributed native binary
and both original historical runtime binaries. The full integration suite
passed1208/1208 in447908.1966ms, with no failures, skips or cancellations.
[Verification data](debugwire-admission-20261024.json) records exact source,
runtime, environment and raw TAP identities, along with each test summary.

Reproduction from the repository worktree:

```powershell
node web-player/scripts/build-device-wasm.mjs
node --test web-player/tests/device-debugwire-config.test.mjs web-player/tests/attiny13a-package.test.mjs web-player/tests/attiny13a-package-runtime.test.mjs
node --test web-player/tests/*.test.mjs
```

The rebuilt runtime is112674 bytes, SHA-256
`d7be3a7378d14c2896a92106291715ed8fcb0d291359e5153efb639f9c18e0a8`.
It retains103 function exports plus memory, no imports and fixed two-page
(131072-byte) memory. This32-byte increase is a correctness change; no execution
speed benefit or additional completed hardware-support item is claimed.
