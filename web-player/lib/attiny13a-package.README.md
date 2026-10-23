# ATtiny13A package format v1

`attiny13a-package.js` creates and verifies a self-contained initial device image.
It has no Node imports and uses asynchronous WebCrypto SHA-256, so the same
module works in Node 22 and browsers in a secure context. It never constructs
a `WebAssembly.Instance`.

```js
import {createPackage, decodePackage, assertPackageRuntimeABI}
  from './attiny13a-package.js';

const pkg = await createPackage({
  flash, eeprom, configuration, translated, runtime, manifest,
});
const savedJSON = JSON.stringify(pkg);
const decoded = await decodePackage(savedJSON);
// decoded: flash/eeprom/translated/runtime Uint8Arrays, configuration, options,
// manifest, abi and integrity. options is a separate configuration copy.
```

`flash` contains 1–1024 bytes and is padded to 1024 with `0xff`. Optional
`eeprom` must contain exactly 64 bytes; omission creates an erased image.
`translated` and `runtime` are WASM bytes. Optional `manifest` must equal the
translation's embedded `micromusic.avr` manifest. No files or URLs are referenced
by the saved package.

The envelope identifies format `micromusic-attiny13a-package`, version `1`,
device `ATtiny13A`, and ABI `micromusic-attiny13a-device-v1`. Each of the four
binary assets records its length, canonical base64 and SHA-256. The envelope
hash covers all fields except `integrity`, including configuration, manifests
and asset hashes. Hash input is UTF-8 JSON with recursively sorted object keys,
preserved array order and standard JSON scalar encoding. Pretty-printing or
object key order does not change integrity.

The loader rejects unsupported identities, missing/unknown envelope fields,
invalid configuration, noncanonical base64, changed bytes/hashes, inconsistent
Flash instruction words, differing embedded/outer manifests and incompatible
WASM interfaces. It verifies fixed unshared wasm32 memory, the full-device
function signatures, no runtime imports, only expected translation imports,
and no WASM start section. Both binaries must pass the engine's validation.
Limits are 1024-byte Flash, 64-byte EEPROM, 4 MiB translation, 2 MiB runtime,
512 KiB embedded manifest and 16 MiB JSON. These are format limits, not device
performance promises.

SHA-256 detects corruption and inconsistent components. An author can modify
code and recompute its hashes. This is not a signature, a trust decision, or a
proof that the translated machine code implements the supplied Flash. Loading
unknown packages still means loading executable WASM.

The declared C data layout cannot be inferred from arbitrary WASM function
bodies without executing them. After verifying the package, the integrating
loader must instantiate its runtime and call
`assertPackageRuntimeABI(decoded, runtimeABI(runtimeInstance.exports))` before
constructing the translated instance. This checks the live state offsets,
memory regions and device marker against the translation. The package API
does not instantiate the device, change default engine selection, or fetch an
external runtime.

## Reproducible configuration

All configuration keys are stored, including defaults. Unknown keys are
rejected. This represents the configured deterministic digital/analog profile;
it does not assert complete silicon behavior or measured oscillator calibration.

| Fields | Default | Accepted values |
|---|---:|---|
| `oscillatorHz` | 9600000 | integer 1–1000000000 |
| `watchdogHz` | 128000 | integer 1–1000000000 |
| `vccMicrovolts` | 5000000 | integer 1–2147483647 |
| `bandgapMicrovolts` | 1100000 | integer 1–2147483647 |
| `fuseLow`, `fuseHigh`, `lock` | 122, 255, 255 | integer 0–255 |
| `adcFirstSample` | 27 | 27 or 29 (half ADC periods) |
| `comparatorPropagationHalf`, `bandgapStartupHalf` | 0 | uint32, runtime half-clock domain |
| `comparatorInitial` | 0 | integer 0 or 1 |
| `wakeStartupHalf` | 0 | uint32, base half ticks |
| `spmCommandCycles` | 0 | uint32; 0 keeps missing timing explicit |
| `flashMaximum` | 1 | integer 0 or 1 |
| `bodRecoveryNs` | 60000 | uint32, nanoseconds |
| `factoryOsccal96` | 0 | integer 0–127, caller-supplied fixture byte |
| `fuseStartupProfile` | 0 | integer 0 or 1 |

## CLI

```sh
node web-player/scripts/package-attiny13a.mjs pack firmware.hex firmware.attiny13a.json
node web-player/scripts/package-attiny13a.mjs pack firmware.bin firmware.attiny13a.json --eeprom eeprom.bin --configuration config.json
node web-player/scripts/package-attiny13a.mjs verify firmware.attiny13a.json
node web-player/scripts/package-attiny13a.mjs unpack firmware.attiny13a.json extracted-device
```

`pack` normally compiles Flash using the repository's bundled full-device
runtime, first checking the runtime's build hash. An existing pair can be
provided with `--translated firmware.wasm --runtime runtime.wasm`; this path
does not instantiate either module. `--no-flag-dce` applies only when compiling.
The generated package is verified again before writing. Output files and the
unpack destination directory must be new. `verify` and `unpack` load and verify
all bytes without running WASM; failed verification creates no extraction
directory. JSON status goes to stdout, errors to stderr with exit status 1.
Unpack emits Flash, EEPROM, both WASM binaries, configuration, manifest and a
small package metadata report.

Primary format references: [WASM binary module grammar](https://webassembly.github.io/spec/core/binary/modules.html)
and [WebCrypto digest / SHA-256](https://www.w3.org/TR/2017/REC-WebCryptoAPI-20170126/#SubtleCrypto-method-digest).
The device configuration follows the repository's documented ATtiny13A runtime
profile; the official device reference is
[Microchip DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf).
