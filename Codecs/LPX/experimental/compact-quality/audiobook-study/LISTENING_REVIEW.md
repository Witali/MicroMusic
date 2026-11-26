# Listener feedback on development example 3

On 2026-11-26, after hearing the last local comparison, the user reported that
**both the current P3 and the automatically selected version were unintelligible**.
This establishes no relative preference between them. The example is not an
audibly confirmed quality improvement, despite its lower measured error and
higher STOI. The saved automatic-selection result remains an algorithmic result.

Read-only follow-up checks found:

- All three source/current/selected WAVs match their retained export receipts
  and exact prepared/native PCM payloads. Each is 160,000 mono PCM16 samples
  at 8 kHz, lasting 20 seconds.
- Neither decoded file clips. RMS levels are source -29.32 dBFS, current
  -30.29 dBFS and selected -29.99 dBFS. These levels alone do not establish
  intelligibility or explain the listening report.
- The original source file is unchanged and matches its frozen fingerprint.
  Repeating the registered preparation reproduces the 8-kHz reference
  byte-for-byte. No new LPX encoding or candidate search was performed.
- A separate 20-second reference at the original 44.1-kHz stereo rate was
  extracted without source metadata or level fitting, for comparison with
  the prepared 8-kHz reference. Both references remain ignored local media.
- Original-channel correlation is .99977; arithmetic mono mixing changes
  the channel RMS by less than .001 dB. No substantial stereo phase
  cancellation was observed in that check.

Export identity and decoder/model agreement establish correct reproduction
of the measured signals; speech quality still requires listening evidence.
The user subsequently confirmed both original-rate and prepared references
intelligible. The problem therefore occurs after LPX processing in this example.
The separate [intelligibility investigation](../../intelligibility/README.md)
records the bounded diagnosis and candidate correction. No source membership,
guard or historical held-out result was changed.
This feedback is an informal local listening observation, not a controlled
listening-test score.
