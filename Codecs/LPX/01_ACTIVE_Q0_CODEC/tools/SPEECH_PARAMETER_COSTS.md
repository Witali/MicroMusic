# Exact hypothetical parameter costs

`speech_parameter_costs.py` measures thirteen predeclared syntax sketches. It
does not encode a new audio format, modify an MCU decoder or emit new streams.
The costs preserve every stored v5 tuple, including unused lag when gain is 0
and the mandatory unplayed tail.

The seven repeat methods select every nonempty scale/lag/gain mask. For a
selected field, a later tuple spends one flag bit and then its existing 5/7/3
absolute bits only when changed. Unselected fields stay absolute. The six
Rice methods select scale+gain or all three fields, with common k=0/1/2. A normal
zigzag delta with quotient q<8 costs q+1+k bits, matching `putrice`; q>=8 spends
exactly eight zero escape bits followed by the complete absolute field value.
That escape is explicitly absolute, unlike v5's escaped zigzag literal.

Every segment starts with an absolute 15-bit tuple. The primary hypothesis
keeps the existing 22-byte-shaped header and charges one extra method-selector
byte. A future format would need its own version/syntax definition; no existing
v5 flag is silently reassigned. Methods have fixed selector IDs 1..13. There is
no per-frame alignment; each segment pays its exact final byte padding.

`inspect_stream` validates existing v5 and uses a second bit cursor to count its
actual consumed payload. It retains spectral Rice choices, the original extras
flag and every marker, including legal marker 1 / amp 0. It does not normalize or
repack the source. `stream_cost` replaces only actual 15-bit tuple fields;
`chain_cost` sums independently padded complete streams. Cached inspections are
bound to their source bytes by a private hash that is not part of cost results.

The signed saved-byte result is a **data-only optimistic allowance** for added
decoder Flash before paying code, tables or layout effects. It is not a measured
firmware saving. A negative result requires program savings elsewhere even to
break even. The optional `min(v5,new)` data envelope also ignores the code cost
of supporting both formats and must be labeled separately. Actual full linked
Flash, SRAM, stack, malformed input behavior and active-IRQ timing are future
acceptance requirements.

Repeat-scale can reuse the derived `blockStep_` value. Raw scale deltas cannot
recover exact previous code from that value because the scale table has aliases.
The existing lag 0 reset sentinel may identify the first new-format tuple only
in the v5-style parameter lifetime: it must be sampled before lag is overwritten.
This is a read-only design observation, not an implementation or size claim.


## Untested selector placement and first-tuple state

The charged byte could begin the new version's payload and be included in the
existing uint16 payload length. Total storage stays 22 + 1 + body; this changes
no measured cost or nomination. A fixed scale-repeat-only prototype could
validate selector 1 once, discard it, and retain the existing derived step on
repeats. No dynamic method/raw-scale member is required by that restricted
idea, but actual code, stack and Flash costs remain unmeasured.

In current `Lpx4HybridCore.cpp`, reset initializes decoded lag to 0 (142/145),
every begin resets state (204), and a v5 tuple stores lag 18..145 (421), including
when gain is 0. Capture that sentinel before assigning the new lag. Encoded lag
code 0 is valid and means lag 18. The invariant does not mark first output in
legacy raw v2/v3 modes. Failed begin, sticky errors and value-copy contracts
must be preserved. Derived step 0 cannot be a first-tuple sentinel because
legal raw scales 0..5 alias to 0. These are read-only lifetime facts, not a
new-format implementation or an SRAM/Flash improvement claim.
