# Canonical retention: complete-player results

The final 118-record replay produced four genuinely new automatic selections
across seven cap views. Their four exact declared-level rollbacks give eight
ordered chains and 16 logical IRQ rows. Three speech selections fit and passed
both IRQ loads. The fourth selection and its rollback cannot fit this device.

| Pair | Rollback → selected data, B | Full Flash, normal IRQ, B | Full Flash, +100 IRQ, B | Growth, B |
|---|---:|---:|---:|---:|
| 001 | 3361 → 3365 | 7934 → 7938 | 7942 → 7946 | +4 |
| 002 | 3328 → 3330 | 7902 → 7904 | 7910 → 7912 | +2 |
| 003 | 1696 → 1697 | 6270 → 6270 | 6278 → 6278 | 0 |
| 004 | 202600 → 202600 | No fit: data alone | No fit: data alone | Unavailable |

Each speech pair is selected at the 95% serialized-data cap in both screen and
default phases: six overlapping views, three distinct comparisons. The cap is
relative to the original encoded-data budget. These results do not establish
5% savings against the already accepted rollback or against full firmware.

The nonspeech pair at the 100% data cap preserves all 60 resets and 3,786,111
samples. Its 202,600 stream bytes alone exceed 32,768 B, before code and metadata.
Both IRQ rows of both chains are `no-fit-data-alone`; no image was built, no
playback support is claimed and unavailable full Flash remains null. A host
data-cap selection is therefore distinct from hardware admission.

The 12 admitted rows comprise six new selected images and six exact rollback
reuses from the completed prior union. All 640,000 physical PWM samples were
checked, equally split between new images and strict reuses. Model/common/v5
PCM16 and PWM agree; produced/played/timer counts cover every whole chain. EOF,
empty final queue and stack checks pass, with zero underruns or decoder/observer
errors. Static SRAM is 756 B and minimum observed stack margin is 1,231 B.
The largest admitted image uses 7,946 B full Flash. Program Flash changes are
0, 0 and −1 B respectively; complete Flash includes the actual linked layout.

Both worker attempts completed without retries: 16.97 s for the reuse shard and
64.78 s for the new-image shard. The subsequent aggregate and artifact export
were read only. No new fits/refinements, decoder/C/ASM changes, source mutation,
trimming or further images occurred.

Scope remains ATmega328P/AVR5, 16 MHz/8 kHz, explicit ASM, queue 256/prefill 192,
IRQ 0/+100 in simavr. No C-backend or physical-board real-time claim follows.
The earlier target A/B listening result remains inconclusive; this admission
does not adopt a larger variant perceptually or remeasure quality.
