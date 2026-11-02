# AVR8js 0.21.1 runtime subset

The project already pins this MIT-licensed package for its ATmega328P Speex
CPU/player verification. `original/` contains the exact six required installed
ES module files. `browser/` changes only their two relative import specifiers
to include `.js`, so native browser modules and Node resolve the same files.
No instruction, timer, GPIO or EEPROM implementation was edited. Preserve the
original copyright headers and [MIT license](LICENSE).

[Provenance](provenance.json) records the upstream package URL, the existing
lockfile's archive SRI, and actual copied/adapted file hashes. The installed
copy was retained locally; the archive SRI is not presented as a fresh archive
verification. Project hardware integration and interrupt-entry timing correction
live separately in `lib/atmega328p.js`.

The package metadata file is not needed by the browser and is not copied.
Only the CPU, instruction/interrupt, timer, GPIO and EEPROM runtime modules
are included; this subset does not claim every ATmega328P peripheral is present.
