MIDI binaries are not retained. source-events.json preserves all SMF events, tracks and original file SHA-256; read with tools/midi-events.py.

Входной файл пользователя: mozart - Turkish March in Eb.mid.
source-events.json сохраняет события оригинала в структурированном виде; атрибуция из MIDI:
  Mozart: Sonate KV 331, 3. Satz
  MIDI Copyright © 2005 Bernd Krüger, http://www.piano-midi.de
  Edition: 2013-07-15

Это исходник аранжировки, а не прошивка. Его полный объём не помещается
в ATtiny13A. Текущая адаптация использует начальные 74 такта 2/4,
шестнадцатую сетку, постоянный темп и отдельную завершающую каденцию.
Скрипт: tools/arrange-turkish-march.py.

Updated native adaptation:74 source2/4bars (148quarters) plus a four-quarter
closing cadence,60.397seconds at steady151BPM. It retains the selected
right-hand melody and bounded bass identities, and restores37 second
left-hand chord tones sharing the selected bass note's original on/off.
Three real piano oscillators replace the former two-primary/two-tail mix.
Other full-source chord tones and later sections remain explicitly omitted.
