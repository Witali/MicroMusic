# NVM voltage uncertainty

`nvm_voltage_uncertain(n, mask)` latches EEPROM128 and/or Flash256 fault bits
only for a currently active operation. The supply owner selects the mask; the
NVM module does not invent an analog failure threshold. The affected operation
remains pending and no longer commits bytes through `nvm_advance`, including
implicit advances in reads, writes, SPM/LPM and reset. Its deadline is removed
from scheduling to avoid retrying a permanently frozen completion. Uncertainty
survives CPU reset; only a new `nvm_init` clears it. Other register controls and
the temporary page buffer still follow their documented reset rules.

Preserved bytes are the last known image, **not** a prediction of corrupted
physical cells. Applications must report the sticky fault rather than use them
as a guaranteed result. This avoids both invented successful programming and
invented random/erased bit patterns.

[DS80000857A2.2.1](https://www.microchip.com/DS80000857), p3, says EEPROM
writes below1.9V might fail for silicon revisions G/H/I.
[DS40002307A](https://ww1.microchip.com/downloads/en/DeviceDoc/ATtiny13A-Data-Sheet-DS40002307A.pdf)
§5.3.6 p25 and §16.7 p107 allow an in-flight write to complete through reset
only while supply is sufficient. A normal reset therefore preserves adequate
voltage programming; a supply-profile failure is handled separately. The
Flash supply boundary is a caller-selected programming profile and is not
automatically assigned the EEPROM erratum's1.9V threshold.
