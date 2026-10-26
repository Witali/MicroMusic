# Normalize personal build paths in retained evidence

A local scan found personal home-directory prefixes in ten tracked files:
four compiler link maps, four profiler function catalogs and two historical
music import/reference notes. The current files replace 2504 such prefixes
with `<local-home>`. The [normalization record](profile-path-normalization-20261026.json)
lists repository paths and before/after hashes without retaining account names.

Only those prefixes changed in the ten original files. Two dependent evidence
manifests now hash the normalized bytes. Function indices, addresses, ownership,
instruction bytes, sample counts, timings and measured conclusions are unchanged.
Native and generated production WASM are unchanged.

The profiling producer now retains object basenames in both its link map and
function catalog. Deterministic tests check Windows/POSIX separators, both line
endings, symbol/address preservation and idempotence. Existing actual generated
CPU dispatch naming checks remain in the same focused suite.

This commit does not remove the original paths from earlier Git history. A
future push/publication must inspect every newly exposed commit/ref as required
by `AGENTS.md`; redacting the latest tree alone cannot satisfy that check.
