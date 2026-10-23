# Speex AVR agent handoff (English summary)

This archive preserves **all nine Speex AVR development stage ZIPs byte-for-byte** and unpacks their contents. Target ATmega328P 16MHz / 2KB SRAM / 32KB flash; Speex narrowband mode 3, 8 kHz, 8 kbps, 20 bytes/20 ms.

**Two distinct branches:** `UNPACKED/08_R4_Cache10Fused_REFERENCE` is a frozen custom/restricted decoder used for regression and benchmarking. `UNPACKED/09_Xiph_Upstream_Port_WIP_ACTIVE` is the **active** upstream port project based on Xiph Speex 1.2.1; it contains optional patches for exact compact LSP→LPC (624→88B temporary polynomials; 240k coefficient-set comparisons), AVR 16/32-bit types, MUL/MULS/MULSU and an experimental shorter excitation buffer. Do NOT conflate the two branches.

**Not completed:** full upstream library is not bundled because the original tarball was not available in the environment; download script and expected SHA256 are in the active branch. Scratch management/PROGMEM and complete avr-gcc linking remain pending. Prior cycle results are LLVM AVR model estimates for R4, NOT measurements of upstream Speex on hardware. No authentic RU/EN human voice files were downloaded in the experiment, but retrieval scripts and source links are in the project.

Read `README_START_HERE_RU.md`, `HANDOFF/01_CURRENT_STATUS_RU.md`, and `HANDOFF/03_NEXT_AGENT_CHECKLIST_RU.md` first.
