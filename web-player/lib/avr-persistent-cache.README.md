# Persistent ATtiny13A translation cache

The full-device renderer uses IndexedDB at construction time to reuse generated
WASM across Worker restarts. The simplified site engines and self-contained
packages retain their existing paths. No emulated instruction, peripheral
event, CLK transition or audio callback accesses storage.

`localStorage` belongs to `Window`, is synchronous, and stores strings.
The emulator executes in a Worker. IndexedDB is available to Workers, accepts
binary structured-clone values, and provides transactions for concurrent
lookup/eviction. See the official [HTML storage API](https://html.spec.whatwg.org/multipage/webstorage.html#the-storage-interface)
and [IndexedDB API](https://www.w3.org/TR/IndexedDB-3/#dom-windoworworkerglobalscope-indexeddb).
This choice is about API fit; performance still requires measurement.

Only generated WASM bytes and small JSON identity metadata are persisted.
`WebAssembly.Module` is not a portable IndexedDB storage format: the current
[WebAssembly Web API serialization algorithm](https://www.w3.org/TR/wasm-web-api-2/#serialization)
rejects serialization with `forStorage=true`. Live instances, memory, register
state, peripheral queues and self-programmed Flash are never persisted.

## Identity and validation

The key hashes the padded initial Flash, initial EEPROM, exact native runtime,
normalized hardware configuration (including fuse/clock profiles), CPU policy,
target/frequency, record version and generated compiler identity. The latter
hashes every JS source under `lib/`, excluding its generated result, plus its
generator. After changing these sources, run:

```text
node web-player/scripts/generate-avr-cache-identity.mjs
node web-player/scripts/generate-avr-cache-identity.mjs --check
```

Deploy a coherent source/native build; the generated identity is a build
invalidation mechanism, not a signature or source attestation. Input buffers
and options are copied before asynchronous work. Native modules are compiled
from the exact bytes hashed for the key.

Each hit verifies recipe equality, bytecode SHA-256 and the package validator's
complete executable checks: all 512 Flash words, embedded manifest, imports,
exports/signatures, fixed memory/table geometry and continuation layout.
The instantiated native ABI must also match before linking. The compiler
policy must equal the requested policy. Hashes detect corruption and stale
components; they do not authenticate arbitrary executable code.

A hit bypasses translation but constructs a fresh complete chip. CPU SPM keeps
its existing generation/image invalidation and retranslation behavior; the
durable record retains only the original immutable image. Region-level
retranslation remains planned.

## Limits and fallback

The database `micromusic-avr-translations-v1` holds at most eight entries and
16 MiB of metadata UTF-8 plus WASM bytes. These are logical payload limits;
browser database overhead is additional. Least-recently-used eviction and
insertion share one transaction, including across Worker connections. The
record schema is `micromusic-avr-cache-v2`; incompatible records are repaired.

Unavailable/denied/blocked storage, one-second storage timeouts, corruption
and quota errors fall back to ordinary full-device construction. They never
select a weaker model. Real firmware/configuration errors still propagate.
Custom runtime/callback options bypass persistence, and `cacheTranslation:false`
explicitly disables it. `core.persistentTranslationCache` and the Worker's
`ready.translationCache` expose construction diagnostics without product UI.

Node normally has no IndexedDB and retains ordinary construction/process
caching. Tests can inject a compatible store through `createCachedDeviceCore`.
See [the measured browser comparison](../reports/persistent-cache-20261026.md)
for the accepted binary format and the rejected full-JSON experiment.
