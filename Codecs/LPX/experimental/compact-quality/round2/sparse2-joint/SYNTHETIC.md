# Joint coordinate rescue before speech

The four synthetic tests pass against both unchanged native C receivers.
The fixed 641-sample fixture has real incoming state from its first 320 samples,
nonzero de-emphasis/brightness, and a real one-sample final tail. The actual
registered frame-priority rule selects the rescue frame; its metadata and
common pulse pools are recomputed from the fixed target.

| Choice in frame 1 | Scale / actual gain | Pulse tuple | Complete PCM SSE |
| --- | --- | --- | ---: |
| Protected original | 15 / 14 | 39,5,9,2 | 7,612,088 |
| Coordinate metadata then pulses | 15 / 14 | 39,5,9,2 | 7,612,088 |
| Coordinate pulses then metadata | 15 / 14 | 39,5,9,2 | 7,612,088 |
| Joint Cartesian | 14 / 14 | 39,5,10,2 | 6,720,780 |

The original is a minimum over BOTH finite coordinate axes on the identical
full-suffix PCM-SSE grid. Both two-sweep controls remain there; the joint point
improves it. This establishes a finite coordinate-rescue mechanism, without the
prior study's prefix/full-suffix objective confound. It is not a global optimum
over all legal fields or evidence of an audible improvement in speech.

The source is deliberately adversarial. An offline bounded Voronoi half-space
construction used actual decoder waveforms and positive rounding margins.
The test stores only its final fixed Q16 integer recombination and reruns no LP.
A preliminary exact-output-target grid did not find the strict rescue. A first
longer construction had a rescue outside the actual two-frame priority set and
was rejected by the test; the final 641-sample fixture satisfies actual search
selection. No search geometry, pool, objective or admission threshold changed.

All 324 leaves and 323 unique native points match complete independent-model,
common-C and v5-only-C PCM/PWM output and EOF. Additional checks cover actual
saturation, gain 0 to 2 and gain 2 to 0 with unchanged lag bits, legal gain-code
mapping, nonminimal Rice spelling, protected partial frames and malformed
patch calls. Independent full-model comparisons establish metadata-conditional
incoming h/ring/dd/cc snapshots for later pulse screens. All three arms have
the same 12-proposal complete-metric cap and protected baseline floors.

The final run passed 4/4 in 1.487 seconds with Python 3.12.10 / NumPy 2.5.4. Complete
software hashes, counts and native bridge evidence remain under ignored
`build/compact-quality/sparse2-joint-tests/tests.json`. These are synthetic host
checks, not a timing benchmark or AVR/physical-board admission.
