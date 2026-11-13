# Sparse80 whole-corpus quality experiment

The opt-in header/beam/local encoder search did **not** meet the requested
majority-improvement goal. It is not selected by default. Listening also rejected
a later local-pulse example because its rasp became higher and more noticeable.
Numerical improvement is not a claim of cleaner perceived sound.

## Fixed scope and results

- 181 whole recordings, 306 bounded segments, 15,188,029 samples at 8 kHz;
  49 speech and 132 music/instrument recordings. A whole recording gets one vote.
- Identical total compressed size: 400,876 bytes before and after. There is one
  whole-record rollback when joining independently improved segments fails a
  whole-record floor.
- 85 recordings change PCM16; only 78 change the actual PWM output. Seven meet
  the declared material PWM proxy (at least 0.1 dB SER or 0.005 STOI improvement).
  Neither 78/181 nor 7/181 is a majority. Perceived-quality majority is unknown.
- Aggregate PWM SER changes from 0.34004 to 0.37751 dB; speech mean PWM STOI
  changes from 0.651746 to 0.652162. These small aggregate changes do not resolve
  the reported rasp. Floors cover native PCM, PWM, available STOI, period
  coverage/error, clipping and a joint proxy. This run has **no upper-band
  specific admission floor** and must not be retroactively described as having
  the later frequency guard.

[Full anonymous numerical results](quality-summary.json) contain no media,
source-media hashes, names or filesystem locations. The ordinal is only a local
vote index. Missing STOI stays missing; membership is fixed from the baseline.
SER is calculated from summed reference/error energy, not averaged dB values.

The fixed search snapshot is the implementation introduced by `47026d7c`;
the export implementation is `02064ecd`. The report records code hashes.
Baseline encoding uses all three pre-emphasis values 13926, 11469 and 8192,
both gamma values 0.97 and 0.94, and a 2 kbit/s size ceiling. This is distinct
from the faster one-pre-emphasis public listening recipe. An ignored exact
loss-pruning implementation accelerated baseline construction: 312 kernel
comparisons and three full encodes retained identical choices and native output.
It is not an active decoder or encoder change.

## Playback verification of this frozen experiment

[IRQ summary](irq-summary.json) is explicitly bound to decoder `95346ea9`.
It covers all 171 changed encoded segments and six unchanged cohort controls
(9,100,022 samples), not every unchanged segment. Every verified stream matches
the C PWM reference, has no underruns, and passes the reserved-register/no-MUL
audit. AVR-GCC 7.3.0, ATtiny88 at 16 MHz, simavr 1.6, 8 kHz output, FIFO 32 and
prefill 24: maximum mean active decoder CPU plus full IRQ is 1744.049381 cycles
per sample; IRQ is 38 cycles; minimum measured stack margin is 11 bytes.
This does not meet 1500 cycles/sample and is not a physical-board measurement.
The maximum complete experimental image is 7526 bytes; this corpus stress run
does not admit every recording under the separate 6.5 KiB application budget.

One transient Windows summary-file sharing failure was retried successfully.
It was an infrastructure incident, not an audio failure. Raw inputs, individual
media hashes, source locations and detailed experiment artifacts remain in
ignored local build storage.
