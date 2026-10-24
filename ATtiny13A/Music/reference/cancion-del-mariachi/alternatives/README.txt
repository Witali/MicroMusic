COMPARISON OF MARIACHI ARRANGEMENTS · 2026-10-24

The original retained source is a two-guitar transcription: Gtr.1 Antonio
and Gtr.2 Meysam. Its selected 30-second passage has 117 lead notes and
910 backing notes. Around 6.67..10.48 seconds, Gtr.1 rests while the second
guitar repeats full chord voicings. Lowering that part by 6 dB softens the
balance but does not change the repeated chord pattern.

Reviewed sources:

1. Two-guitar interpretation hosted by Gitaartabs, Solo Guitar/Acoustic Guitar:
https://www.gitaartabs.nl/tab/los-lobos-and-antonio-banderas/cancion-del-mariachi
The Guitar Solo section begins with sustained accompaniment beneath the
triplet solo. Later sections return to denser strums, including muted hits.
This provides a useful sparse-support example, not evidence that the whole
arrangement has sparse rhythm. The author's private-study notice is retained
on that page. No copy of the tab or its note sequences is committed here.

2. Christian's How To Plays, guitar notation/TAB, 126 BPM:
https://christianshowtoplays.de/download/PDF/Los_Lobos_Cancin_Del_Mariachi_antonio_banderas_version.pdf
Pages 1–2 were rendered and visually checked. The score labels Intro, Verse,
Chorus and Interlude; the lead has written rests in the Verse. This is a
useful structural cross-check of the existing lead part, not an independent
proof of soundtrack accuracy. No notes were imported from the PDF.

3. Sungha Jung solo fingerstyle version, nylon guitar:
https://www.songsterr.com/a/wsa/los-lobos-sungha-jung-cancion-del-mariachi-tab-s380875
Publicly readable tab excerpt/mirror:
https://www.scribd.com/document/719644869/Cancion-Del-Mariachi-Tab-by-Sungha-Jung
The single-guitar arrangement combines bass, chord fragments, melodic notes
and muted hits. It is a substantially different fingerstyle adaptation,
not simply a quieter version of the two-guitar score. No complete performance
was downloaded or listened to, and no exact note transcription was imported.

A multitrack karaoke alternative on Karaoplay was also located, but its
current download redirects to login. It was not imported; the temporary
non-MIDI response was removed. No access restrictions were bypassed.

The new sparse-source-voicings-v1 variant is our own adaptation of the
existing source-events.json: retain Gtr.1 exactly; replace Gtr.2 with one
bass note or up to three different chord classes every two quarters,
holding for one quarter and leaving one quarter of rest. Harmony comes
from the active/latest original Gtr.2 voicing. Backing begins only after
that source part enters. No new filler melody is fabricated.

This intentionally reduces backing attacks from 167 to 28 and backing notes
from 910 to 56. The original 1027-note player remains a separate variant.
The new player is not described as lossless relative to both source parts.

The first sparse audition above was subsequently extended to source beat
184 1/3 (tick 88480), ending on E4. It now retains all 261 lead notes over
60.15867 seconds, with 60 backing attacks / 120 backing notes. The earlier
117 lead notes remain an unchanged prefix. Compact variable-length chord
shapes and a gate palette preserve the new triplets, sixteenths and three-note
lead chords. Every build calibrates the complete unscaled AVR output, then
uses fixed linear peak gain x4 around midpoint 128: physical PWM codes 0..248.
At that stage the normalized firmware occupied 1006 Flash bytes; WAV export separately
normalizes the filtered signal to full digital peak. All builders, calibration
and audit scripts are retained under tools/.

At the user's request, the current version also uses the previous ensemble's
GM35 kick and GM42 closed hat, alternating every half-quarter. These are newly
added accompaniment, not an original soundtrack drum transcription. The old
triangle/noise generators and four-stage decay are retained; final quiet gain
rounds to nearest to avoid a persistent negative one-code tail. All 381 guitar
notes are unchanged. Six tonal generators and one drum generator fit in exactly
1024 Flash bytes after moving the 15 pitch steps into 30 free EEPROM bytes.
The complete mix calibrates to PWM 0..252, and the exported WAV to 0 dBFS.
The --no-percussion builder option reproduces the previous minute exactly.
