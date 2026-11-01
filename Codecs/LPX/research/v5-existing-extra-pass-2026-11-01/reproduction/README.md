# Additional preflight admission

The top-level producer and successful v2 metadata/preflight stay frozen at
research commit `5930fa96`. The producer's snapshot enumerates only top-level
files, so this separate entry gate has its own source-bound receipt. It does
not repeat, relabel or change the six successful v2 synthetic calls.

Invoke `admit_preflight.py` for every real worker. It requires the normal
`--source-root`, `--baselines`, `--native-cases`, `--preflight`, `--arm` and
`--output` arguments plus a separate fresh private `--admission-output`.
It checks closed preflight-only summary/attempt/results, all current production,
native, research and recorded runtime fields, and both the resolved prepared
manifest path and its pinned digest. Only after persisting its own complete
admission receipt does it invoke the unchanged producer main with those exact
arguments. Source/input guards are repeated afterward. Admission and worker
costs are recorded separately. Use the same numerical-environment launcher and
keep all artifacts under ignored build directories.

`--admission-only` performs these read-only checks and creates a reviewable
receipt without requiring an arm/output or invoking a helper. The contract file
checks wrong runtime, wrong manifest path/digest, incomplete evidence and changed
source/native context, entirely without codecs or media.

Paid synthetic accounting remains historical six + v2 six + worker warm six =
eighteen, in addition to the fixed twenty corpus calls. Real workers still need
integration review and authorization. No target jobs or extra metrics belong to
this gate.
