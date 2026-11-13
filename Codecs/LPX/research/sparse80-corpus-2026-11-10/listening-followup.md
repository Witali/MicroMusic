# Chego listening follow-up

The later local-pulse candidate is rejected: the listener reported higher,
more noticeable rasp. The tentative later ranking is original low-rate decode,
then a slightly preferred header-only `Improved`, then a possibly slightly
preferred `Low Pass Experimental`. This supersedes the earlier report of almost
no difference for the lowpass example. It is a weak single-clip preference,
not a confirmed improvement on most recordings.

The private lowpass experiment keeps 297 bytes and all filter parameters in the
stream. C PCM16 and actual simulated AVR/IRQ PWM exactly match its model over
9831 samples, with no underruns. It reduces PWM squared error by about 3.04%
and the two tested upper-band errors by about 3.69% and 11.39%; period coverage
is unchanged. Its PWM STOI decreases from 0.656957 to 0.651344, so it fails the
strict numerical quality floor and is not selected by default.

The private universal program is 5625 bytes; the full image is 5922 bytes
(5.783 KiB), including 297 audio bytes. Mean active decoder CPU plus complete
IRQ is about 1646.543 cycles/sample, versus 1546.723 in the private comparison
with brightness zero. This is not a production firmware admission.

Matched-binary controls explain the added cost: the flag check costs exactly
5 cycles when clear or 7 when set; nonzero brightness invokes the existing
14-step software multiplication. With identical candidate state and brightness
magnitude 6144, positive filtering measures 1644.317 cycles/sample and negative
filtering 1646.543. There is no evidence of a lost inline optimization or a new
register spill causing a 100-cycle sign-change cost. The four binaries are
identical outside embedded audio. All these controls have exact C/PWM output
and zero underruns in simavr, with no physical-board measurement.

The lowpass example remains a listening reference for future work on excitation
and cheaper filtering. The production decoder, default encoder and web images
are unchanged by this experiment. Private logs, prototype images and listening
artifacts remain in ignored build storage.
