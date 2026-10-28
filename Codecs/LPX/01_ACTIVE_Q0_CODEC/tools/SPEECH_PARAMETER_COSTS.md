# Exact hypothetical parameter costs

`speech_parameter_costs.py` measures thirteen predeclared syntax sketches. It
does not encode a new audio format, modify an MCU decoder or emit new streams.
The costs preserve every stored v5 tuple, including unused lag when gain is0
and the mandatory unplayed tail.

The seven repeat methods select every nonempty scale/lag/gain mask. For a
selected field, a later tuple spends one flag bit and then its existing5/7/3
absolute bits only when changed. Unselected fields stay absolute. The six
Rice methods select scale+gain or all three fields, with common k0/1/2. A normal
zigzag delta with quotient q<8 costs q+1+k bits, matching `putrice`; q>=8 spends
exactly eight zero escape bits followed by the complete absolute field value.
That escape is explicitly absolute, unlike v5's escaped zigzag literal.

Every segment starts with an absolute15-bit tuple. The primary hypothesis
keeps the existing22-byte-shaped header and charges one extra method-selector
byte. A future format would need its own version/syntax definition; no existing
v5 flag is silently reassigned. Methods have fixed selector IDs1..13. There is
no per-frame alignment; each segment pays its exact final byte padding.

`inspect_stream` validates existing v5 and uses a second bit cursor to count its
actual consumed payload. It retains spectral Rice choices, the original extras
flag and every marker, including legal marker1/amp0. It does not normalize or
repack the source. `stream_cost` replaces only actual15-bit tuple fields;
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
The existing lag0 reset sentinel may identify the first new-format tuple only
in the v5-style parameter lifetime: it must be sampled before lag is overwritten.
This is a read-only design observation, not an implementation or size claim.
