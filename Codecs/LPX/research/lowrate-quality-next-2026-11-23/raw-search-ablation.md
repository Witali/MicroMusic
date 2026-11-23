# Raw strict-3k search ablation

Three public jobs and two already-known development jobs compared the composite
candidate with a private build that omitted only its three additional raw-3k
regeneration passes. Both header passes, the LPC stage, complete V3 incumbent,
selection gates and file caps remained unchanged. No new-primary material was
read.

**All five pairs produced identical complete LPX bytes, decoded PCM/PWM and
common metrics.** All five complete-file caps were retained. The extra raw
search supplied no selected quality or size benefit in this cohort.

Reported API totals were 114.7499 seconds with raw regeneration and 58.9826
seconds without it, a paired difference of 55.7673 seconds. Each variant ran
once per job, with alternating pair order and other authorized work running
concurrently. These are noisy single observations, not a benchmark or speedup
bound.

This evidence motivated removing the extra regeneration and its unused visitor
API while retaining the header/LPC proposals. It establishes equivalence for
these five known jobs, not all valid inputs. [Aggregate results](raw-search-ablation.json)
contain no per-record identities or media bindings.
